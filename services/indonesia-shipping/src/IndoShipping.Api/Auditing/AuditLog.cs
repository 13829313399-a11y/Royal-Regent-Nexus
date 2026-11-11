using System.Data;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text.Json;
using Dapper;
using Microsoft.AspNetCore.Mvc;

namespace IndoShipping.Api.Auditing;

public static class AuditLog
{
    public static Task WriteAsync(
        this ControllerBase controller,
        IDbConnection connection,
        IDbTransaction? transaction,
        string module,
        string action,
        string entityType,
        object? entityId,
        string summary,
        object? details = null)
    {
        var idText = controller.User.FindFirstValue(ClaimTypes.NameIdentifier)
                     ?? controller.User.FindFirstValue(JwtRegisteredClaimNames.Sub);
        var isNexus = controller.User.FindFirstValue("nexus_bridge") == "1";
        int? userId = !isNexus && int.TryParse(idText, out var parsed) ? parsed : null;
        var nexusUserId = isNexus ? idText : null;
        var nexusFactoryId = isNexus ? controller.User.FindFirstValue("nexus_factory") : null;
        var nexusEmploymentEpoch = isNexus ? controller.User.FindFirstValue("nexus_employment_epoch") : null;
        var actorDisplayName = isNexus ? controller.User.FindFirstValue("nexus_display_name") : null;
        var username = controller.User.FindFirstValue(ClaimTypes.Name) ?? "";
        var ipAddress = controller.HttpContext.Connection.RemoteIpAddress?.ToString() ?? "";
        var detailJson = details is null ? null : JsonSerializer.Serialize(details);
        var identityColumns = isNexus ? ", nexus_user_id, nexus_factory_id, nexus_employment_epoch, actor_display_name" : "";
        var identityValues = isNexus ? ", @nexusUserId, @nexusFactoryId, @nexusEmploymentEpoch, @actorDisplayName" : "";

        return connection.ExecuteAsync($@"
            INSERT INTO audit_logs(
                user_id, username, module, action, entity_type, entity_id, summary, details, ip_address{identityColumns})
            VALUES (
                @userId, @username, @module, @action, @entityType, @entityId, @summary,
                CAST(@detailJson AS jsonb), @ipAddress{identityValues})",
            new
            {
                userId,
                nexusUserId,
                nexusFactoryId,
                nexusEmploymentEpoch,
                actorDisplayName,
                username,
                module,
                action,
                entityType,
                entityId = entityId?.ToString() ?? "",
                summary,
                detailJson,
                ipAddress
            }, transaction);
    }
}
