using System.Text;
using IndoShipping.Api.Auth;
using IndoShipping.Api.Features.Bootstrap;
using IndoShipping.Api.Startup;
using IndoShipping.Domain.Auth;
using IndoShipping.Infrastructure.Auth;
using IndoShipping.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Authorization;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using Microsoft.OpenApi.Models;

// 实体里的 DateTime 均为 timestamp without time zone，沿用旧 SQL Server datetime 语义。
AppContext.SetSwitch("Npgsql.EnableLegacyTimestampBehavior", true);

var builder = WebApplication.CreateBuilder(args);
var nexusEnabled = builder.Configuration.GetValue<bool>("NexusBridge:Enabled");
if (!nexusEnabled) DeploymentSecrets.TryApplyToConfiguration(builder.Configuration);
var nexusFactory = builder.Configuration["NexusBridge:FactoryId"] ?? "";
var nexusKey = builder.Configuration["NexusBridge:Key"] ?? "";
if (nexusEnabled && (!NexusBridge.Factories.Contains(nexusFactory) || Encoding.UTF8.GetByteCount(nexusKey) < 32))
    throw new InvalidOperationException("Nexus bridge requires an explicit factory and a key of at least 32 bytes");

var connStr = builder.Configuration.GetConnectionString("Default")
              ?? throw new InvalidOperationException("Missing ConnectionStrings:Default");

if (nexusEnabled && string.IsNullOrWhiteSpace(new Npgsql.NpgsqlConnectionStringBuilder(connStr).SearchPath))
    throw new InvalidOperationException("Nexus sidecar requires an explicit PostgreSQL Search Path (for example indo_shipping)");
var jwtOpts = nexusEnabled
    ? new JwtOptions { Issuer = "RoyalRegentNexus", Audience = "IndoShippingNexus", Key = nexusKey }
    : builder.Configuration.GetSection("Jwt").Get<JwtOptions>()
      ?? throw new InvalidOperationException("Missing Jwt section");
if (string.IsNullOrWhiteSpace(jwtOpts.Key) || jwtOpts.Key.Length < 32)
    throw new InvalidOperationException("Jwt:Key must be at least 32 chars");

builder.Services.AddSingleton(jwtOpts);
builder.Services.AddSingleton<IJwtTokenService, JwtTokenService>();
builder.Services.AddSingleton<IPasswordHasher, BcryptPasswordHasher>();
builder.Services.AddSingleton<ISqlConnectionFactory>(_ => new SqlConnectionFactory(connStr));
builder.Services.AddDbContext<AppDbContext>(o => o.UseNpgsql(connStr));

builder.Services.AddCors(o => o.AddDefaultPolicy(p =>
    p.AllowAnyHeader().AllowAnyMethod().AllowAnyOrigin()));

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o =>
    {
        o.TokenValidationParameters = new TokenValidationParameters
        {
            ClockSkew = nexusEnabled ? TimeSpan.FromSeconds(5) : TimeSpan.FromMinutes(5),
            ValidAlgorithms = new[] { SecurityAlgorithms.HmacSha256 },
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = jwtOpts.Issuer,
            ValidAudience = jwtOpts.Audience,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtOpts.Key))
        };
    });

builder.Services.AddSingleton<IAuthorizationHandler, PermissionHandler>();
builder.Services.AddAuthorizationBuilder()
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.Products),    p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.Products)))
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.Materials),   p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.Materials)))
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.Customers),   p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.Customers)))
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.Schedules),   p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.Schedules)))
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.Purchase),    p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.Purchase)))
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.Quotes),      p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.Quotes)))
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.MoldingPos),  p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.MoldingPos)))
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.Outbound),    p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.Outbound)))
    .AddPolicy(PermissionHandler.PolicyName(PermissionPosition.Shipments),   p => p.Requirements.Add(new PermissionRequirement(PermissionPosition.Shipments)));

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(c =>
{
    c.SwaggerDoc("v1", new OpenApiInfo { Title = "IndoShipping API", Version = "v1" });
    c.AddSecurityDefinition("Bearer", new OpenApiSecurityScheme
    {
        Name = "Authorization",
        Type = SecuritySchemeType.Http,
        Scheme = "bearer",
        BearerFormat = "JWT",
        In = ParameterLocation.Header
    });
    c.AddSecurityRequirement(new OpenApiSecurityRequirement
    {
        [new OpenApiSecurityScheme
        {
            Reference = new OpenApiReference { Type = ReferenceType.SecurityScheme, Id = "Bearer" }
        }] = Array.Empty<string>()
    });
});

var app = builder.Build();

// 首次启动建表（共享 PostgreSQL 不能用 EnsureCreated）+ 幂等种子导入。
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    if (nexusEnabled)
        await NexusBridge.BindDatabaseAsync(db, nexusFactory, app.Configuration.GetValue<bool>("NexusBridge:AdoptExistingDatabase"));
    await DatabaseCompatibility.EnsureAsync(db, nexusEnabled);
    var passwordHasher = scope.ServiceProvider.GetRequiredService<IPasswordHasher>();
    await ProductionSeeder.SeedAsync(db, app.Configuration, passwordHasher, app.Logger);
    await DataMigrations.ApplyAsync(db, app.Logger);
}

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

// 云端反向代理会剥离 /indo-shipping；本机直连 5180 时保留该前缀。
// 同时接受两种入口，避免前端资源在本地直连时返回 404 白屏。
app.UsePathBase("/indo-shipping");
app.UseRouting();
if (!nexusEnabled) app.UseCors();
app.UseAuthentication();
if (nexusEnabled)
{
    app.Use(async (context, next) =>
    {
        if (context.Request.Path == "/healthz") { await next(context); return; }
        if (context.User.Identity?.IsAuthenticated != true ||
            context.User.FindFirst("nexus_bridge")?.Value != "1" ||
            context.User.FindFirst("nexus_factory")?.Value != nexusFactory)
        {
            context.Response.StatusCode = 401;
            await context.Response.WriteAsJsonAsync(new { error = "仅允许已授权的 Nexus 厂区入口" });
            return;
        }
        if (context.Request.Path.StartsWithSegments("/api/auth", StringComparison.OrdinalIgnoreCase) ||
            context.Request.Path.StartsWithSegments("/api/users", StringComparison.OrdinalIgnoreCase))
        {
            context.Response.StatusCode = 403;
            await context.Response.WriteAsJsonAsync(new { error = "账号和权限统一由 Nexus 管理，原系统账号功能已停用" });
            return;
        }
        await next(context);
    });
}
app.MapGet("/healthz", () => Results.Ok(new { status = "ready" }));
app.UseMiddleware<ApiPermissionMiddleware>();
app.UseAuthorization();
app.UseDefaultFiles();
app.UseStaticFiles();
app.MapControllers();
app.MapFallbackToFile("index.html");

app.Run();
