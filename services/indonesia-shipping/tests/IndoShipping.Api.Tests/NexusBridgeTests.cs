using System.Security.Claims;
using Dapper;
using IndoShipping.Api.Auth;
using IndoShipping.Infrastructure.Auth;
using IndoShipping.Infrastructure.Persistence;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using Xunit;

namespace IndoShipping.Api.Tests;

public class NexusBridgeTests
{
    [Theory]
    [InlineData("/api/shipments", "GET", "000000001", "000000000", false, false, 200)]
    [InlineData("/api/shipments", "POST", "000000001", "000000000", false, false, 403)]
    [InlineData("/api/shipments", "POST", "000000001", "000000001", false, false, 200)]
    [InlineData("/api/products", "GET", "000000001", "000000001", false, false, 403)]
    [InlineData("/api/products/by-code", "GET", "100000000", "000000000", false, false, 403)]
    [InlineData("/api/products/by-code", "GET", "110000000", "000000000", false, false, 200)]
    [InlineData("/api/products/by-code", "DELETE", "110000000", "100000000", false, false, 403)]
    [InlineData("/api/products/by-code", "DELETE", "110000000", "110000000", false, false, 200)]
    [InlineData("/api/users", "GET", "111111111", "111111111", false, false, 403)]
    [InlineData("/api/db", "GET", "111111111", "111111111", true, false, 403)]
    [InlineData("/api/users", "POST", "000000000", "000000000", true, false, 403)]
    [InlineData("/api/users/me", "GET", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/users/me/password", "POST", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/users/1", "DELETE", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/users/1", "PUT", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/users/1/password", "POST", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/db", "DELETE", "000000000", "000000000", false, true, 403)]
    [InlineData("/api/db", "GET", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/db/customers", "GET", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/db/customers", "POST", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/db/customers/1", "PUT", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/db/customers/1", "DELETE", "111111111", "111111111", true, true, 403)]
    [InlineData("/API/DB/customers", "DELETE", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/db/settings", "HEAD", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/db/settings/1", "PATCH", "111111111", "111111111", true, true, 403)]
    [InlineData("/api/db", "OPTIONS", "111111111", "111111111", true, true, 403)]
    public async Task CanonicalClaimsReplaceLegacyUsersWithoutGrantingImplicitAdmin(
        string path, string method, string access, string edit, bool users, bool database, int status)
    {
        var nextCalled = false;
        var middleware = new ApiPermissionMiddleware(_ => { nextCalled = true; return Task.CompletedTask; });
        var context = new DefaultHttpContext { User = new ClaimsPrincipal(new ClaimsIdentity(new[] {
            new Claim("nexus_bridge", "1"), new Claim(ClaimTypes.NameIdentifier, "nexus-string-id"),
            new Claim(JwtTokenService.PermissionClaim, access), new Claim(JwtTokenService.EditPermissionClaim, edit),
            new Claim("nexus_users_manage", users.ToString().ToLowerInvariant()),
            new Claim("nexus_database_manage", database.ToString().ToLowerInvariant()),
        }, "nexus-test")) };
        context.Request.Path = path; context.Request.Method = method;
        if (method == "DELETE") context.Request.QueryString = new QueryString("?confirm=YES");
        // No database is reachable: trusted Nexus identities must not consult legacy Users.
        await using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>()
            .UseNpgsql("Host=127.0.0.1;Port=1;Database=not-used").Options);
        await middleware.InvokeAsync(context, db);
        Assert.Equal(status, context.Response.StatusCode);
        Assert.Equal(status == 200, nextCalled);
    }

    [Fact]
    public async Task DatabaseBindingIsPersistentIdempotentAndRejectsWrongFactoryBeforeBootstrap()
    {
        var source = Environment.GetEnvironmentVariable("NEXUS_BRIDGE_TEST_CONNECTION");
        if (string.IsNullOrWhiteSpace(source)) return;
        // Create/drop only a uniquely named disposable database, never the configured DB.
        var name = "nexus_bridge_test_" + Guid.NewGuid().ToString("N");
        var adminConfig = new NpgsqlConnectionStringBuilder(source) { Database = "postgres", Pooling = false };
        await using var admin = new NpgsqlConnection(adminConfig.ConnectionString);
        await admin.OpenAsync();
        await admin.ExecuteAsync($"CREATE DATABASE \"{name}\"");
        try
        {
            var config = new NpgsqlConnectionStringBuilder(source) { Database = name, Pooling = false };
            await using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseNpgsql(config.ConnectionString).Options);
            await NexusBridge.BindDatabaseAsync(db, "huaxing", false);
            await NexusBridge.BindDatabaseAsync(db, "huaxing", false);
            await Assert.ThrowsAsync<InvalidOperationException>(() => NexusBridge.BindDatabaseAsync(db, "huadeng", false));
            var connection = db.Database.GetDbConnection();
            Assert.Equal("huaxing", await connection.ExecuteScalarAsync<string>("SELECT factory_id FROM public.nexus_indonesia_factory_binding"));
        }
        finally { await admin.ExecuteAsync($"DROP DATABASE \"{name}\" WITH (FORCE)"); }
    }

    [Fact]
    public async Task UnboundExistingDatabaseNeedsExplicitAdoption()
    {
        var source = Environment.GetEnvironmentVariable("NEXUS_BRIDGE_TEST_CONNECTION");
        if (string.IsNullOrWhiteSpace(source)) return;
        var name = "nexus_bridge_test_" + Guid.NewGuid().ToString("N");
        await using var admin = new NpgsqlConnection(new NpgsqlConnectionStringBuilder(source) { Database = "postgres", Pooling = false }.ConnectionString);
        await admin.OpenAsync(); await admin.ExecuteAsync($"CREATE DATABASE \"{name}\"");
        try
        {
            await using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseNpgsql(
                new NpgsqlConnectionStringBuilder(source) { Database = name, Pooling = false }.ConnectionString).Options);
            await db.Database.OpenConnectionAsync();
            await db.Database.GetDbConnection().ExecuteAsync("CREATE TABLE public.existing_business(id int)");
            await Assert.ThrowsAsync<InvalidOperationException>(() => NexusBridge.BindDatabaseAsync(db, "huaxing", false));
            await NexusBridge.BindDatabaseAsync(db, "huaxing", true);
            Assert.True(await db.Database.GetDbConnection().ExecuteScalarAsync<bool>("SELECT to_regclass('public.existing_business') IS NOT NULL"));
        }
        finally { await admin.ExecuteAsync($"DROP DATABASE \"{name}\" WITH (FORCE)"); }
    }
}
