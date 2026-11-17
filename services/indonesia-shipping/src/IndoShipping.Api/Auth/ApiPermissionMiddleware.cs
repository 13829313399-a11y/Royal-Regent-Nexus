using System.Security.Claims;
using IndoShipping.Domain.Auth;
using IndoShipping.Infrastructure.Auth;
using IndoShipping.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using System.IdentityModel.Tokens.Jwt;

namespace IndoShipping.Api.Auth;

public class ApiPermissionMiddleware(RequestDelegate next)
{
    private static readonly Dictionary<string, int> Modules = new(StringComparer.OrdinalIgnoreCase)
    {
        ["/api/products"] = PermissionPosition.Products,
        ["/api/images"] = PermissionPosition.Products,
        ["/api/dictionaries"] = PermissionPosition.Products,
        ["/api/materials"] = PermissionPosition.Materials,
        ["/api/customers"] = PermissionPosition.Customers,
        ["/api/schedules"] = PermissionPosition.Schedules,
        ["/api/purchase"] = PermissionPosition.Purchase,
        ["/api/material-alerts"] = PermissionPosition.Purchase,
        ["/api/quotes"] = PermissionPosition.Quotes,
        ["/api/molding-pos"] = PermissionPosition.MoldingPos,
        ["/api/outbound"] = PermissionPosition.Outbound,
        ["/api/shipments"] = PermissionPosition.Shipments,
    };

    public async Task InvokeAsync(HttpContext context, AppDbContext db)
    {
        var path = context.Request.Path;
        if (!StartsWithSegment(path, "/api") ||
            StartsWithSegment(path, "/api/auth") ||
            StartsWithSegment(path, "/api/health"))
        {
            await next(context);
            return;
        }

        if (context.User.Identity?.IsAuthenticated != true)
        {
            await Deny(context, StatusCodes.Status401Unauthorized, "请先登录");
            return;
        }

        var isCurrentUserEndpoint = StartsWithSegment(path, "/api/users/me");
        var isAdminEndpoint = StartsWithSegment(path, "/api/users") ||
                              StartsWithSegment(path, "/api/db");
        var match = Modules.FirstOrDefault(x => StartsWithSegment(path, x.Key));
        if (!isCurrentUserEndpoint && !isAdminEndpoint && match.Key is null)
        {
            await Deny(context, StatusCodes.Status403Forbidden, "接口未注册或未配置权限");
            return;
        }

        var isNexus = context.User.FindFirst("nexus_bridge")?.Value == "1";
        if (isNexus && StartsWithSegment(path, "/api/users"))
        {
            await Deny(context, StatusCodes.Status403Forbidden, "账号和权限统一由 Nexus 管理，原系统账号功能已停用");
            return;
        }
        if (isNexus && StartsWithSegment(path, "/api/db"))
        {
            // Never accept a historical database-management claim in Nexus mode.
            await Deny(context, StatusCodes.Status403Forbidden, "原系统数据库管理已停用，请使用对应业务页面维护资料");
            return;
        }
        var access = context.User.FindFirst(JwtTokenService.PermissionClaim)?.Value ?? "";
        var edit = context.User.FindFirst(JwtTokenService.EditPermissionClaim)?.Value ?? "";
        if (!isNexus)
        {
        var idText = context.User.FindFirst(ClaimTypes.NameIdentifier)?.Value
                     ?? context.User.FindFirst(JwtRegisteredClaimNames.Sub)?.Value;
        if (!int.TryParse(idText, out var userId))
        {
            await Deny(context, StatusCodes.Status401Unauthorized, "登录已失效，请重新登录");
            return;
        }
        var currentUser = await db.Users.AsNoTracking().FirstOrDefaultAsync(x => x.Id == userId && x.IsActive);
        if (currentUser is null)
        {
            await Deny(context, StatusCodes.Status401Unauthorized, "账户已停用或删除");
            return;
        }
        access = currentUser.Userbqrpower;
        edit = currentUser.Usereditpower;
        }

        if (isCurrentUserEndpoint)
        {
            await next(context);
            return;
        }

        // Only the original standalone application retains legacy administration.
        if (isAdminEndpoint)
        {
            if (access != "111111111" || edit != "111111111")
            {
                await Deny(context, StatusCodes.Status403Forbidden, "仅管理员可执行此操作");
                return;
            }
            await next(context);
            return;
        }

        if (match.Key is not null)
        {
            if (isNexus && match.Key == "/api/products" &&
                (!Has(access, PermissionPosition.Materials) ||
                 (!IsReadOnlyMethod(context.Request.Method) && !Has(edit, PermissionPosition.Materials))))
            {
                await Deny(context, StatusCodes.Status403Forbidden, "货号库包含物料资料，需要对应物料权限");
                return;
            }
            if (!Has(access, match.Value))
            {
                await Deny(context, StatusCodes.Status403Forbidden, "没有访问该模块的权限");
                return;
            }
            if (!IsReadOnlyMethod(context.Request.Method) && !Has(edit, match.Value))
            {
                await Deny(context, StatusCodes.Status403Forbidden, "该模块为只读权限，不能修改");
                return;
            }
        }

        await next(context);
    }

    private static bool StartsWithSegment(PathString path, string prefix) =>
        path.StartsWithSegments(new PathString(prefix), StringComparison.OrdinalIgnoreCase);

    private static bool Has(string value, int position) => value.Length > position && value[position] == '1';
    private static bool IsReadOnlyMethod(string method) =>
        HttpMethods.IsGet(method) || HttpMethods.IsHead(method) || HttpMethods.IsOptions(method);

    private static async Task Deny(HttpContext context, int status, string error)
    {
        context.Response.StatusCode = status;
        context.Response.ContentType = "application/json; charset=utf-8";
        await context.Response.WriteAsJsonAsync(new { error });
    }
}
