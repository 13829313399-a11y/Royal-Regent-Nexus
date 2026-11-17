using System.Security.Claims;
using System.Text.Json;
using Dapper;
using IndoShipping.Api.Auditing;
using IndoShipping.Api.Auth;
using IndoShipping.Api.Features.Bootstrap;
using IndoShipping.Infrastructure.Auth;
using IndoShipping.Infrastructure.Persistence;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;
using Xunit;

namespace IndoShipping.Api.Tests;

public class NexusAccountCompatibilityTests
{
    private static async Task InDisposableDatabase(Func<AppDbContext, Task> check)
    {
        var source = Environment.GetEnvironmentVariable("NEXUS_BRIDGE_TEST_CONNECTION");
        if (string.IsNullOrWhiteSpace(source)) return;
        var name = "nexus_accounts_test_" + Guid.NewGuid().ToString("N");
        await using var admin = new NpgsqlConnection(new NpgsqlConnectionStringBuilder(source) { Database = "postgres", Pooling = false }.ConnectionString);
        await admin.OpenAsync();
        await admin.ExecuteAsync($"CREATE DATABASE \"{name}\"");
        try
        {
            await using var db = new AppDbContext(new DbContextOptionsBuilder<AppDbContext>().UseNpgsql(
                new NpgsqlConnectionStringBuilder(source) { Database = name, SearchPath = "indo_shipping", Pooling = false }.ConnectionString).Options);
            await NexusBridge.BindDatabaseAsync(db, "huadeng", false);
            await check(db);
        }
        finally { await admin.ExecuteAsync($"DROP DATABASE \"{name}\" WITH (FORCE)"); }
    }

    private static IConfiguration Config(string? path = null, string? seedFactory = "huadeng") =>
        new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> {
            ["NexusBridge:Enabled"] = "true", ["NexusBridge:FactoryId"] = "huadeng",
            ["NexusBridge:SeedFactoryId"] = seedFactory,
            ["SEED_FILE"] = path ?? Path.Combine(Path.GetTempPath(), Guid.NewGuid() + ".absent.json"),
        }).Build();

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task BusinessSnapshotsNeedNoLegacyAccountsAndPreserveExistingUsers(bool includeConflictingUsers)
    {
        await InDisposableDatabase(async db => {
            await DatabaseCompatibility.EnsureAsync(db, nexusBridge: true);
            var connection = db.Database.GetDbConnection();
            Assert.Equal(0, await connection.ExecuteScalarAsync<int>("SELECT count(*) FROM \"Users\""));
            await ProductionSeeder.SeedAsync(db, Config(), new BcryptPasswordHasher(), NullLogger.Instance);
            Assert.Equal(0, await connection.ExecuteScalarAsync<int>("SELECT count(*) FROM \"Users\""));
            // Historical account must remain byte-for-byte unchanged and never be used by Nexus.
            await connection.ExecuteAsync("""
                INSERT INTO "Users" ("Id", "Username", "PasswordHash", "DisplayName")
                VALUES (7, 'historical', 'keep-this-hash', '历史人员')
                """);
            var snapshot = new Dictionary<string, object> {
                ["schemaVersion"] = "nexus-business-only-test",
                ["tables"] = new { customers = new[] { new { id = 42, name = "独立验收客户", created_at = "2026-11-09T00:00:00", active = true } } },
                ["images"] = Array.Empty<object>(),
            };
            if (includeConflictingUsers) snapshot["users"] = new[] { new { items = new[] { new {
                id = 7, username = "conflicting", passwordHash = "must-not-import", displayName = "旧账号",
                userbqrpower = "111111111", usereditpower = "111111111", isActive = true,
            } } } };
            var file = Path.GetTempFileName();
            try
            {
                await File.WriteAllTextAsync(file, JsonSerializer.Serialize(snapshot));
                await Assert.ThrowsAsync<InvalidOperationException>(() => ProductionSeeder.SeedAsync(
                    db, Config(file, "huaxing"), new BcryptPasswordHasher(), NullLogger.Instance));
                Assert.Equal(0, await connection.ExecuteScalarAsync<int>("SELECT count(*) FROM customers"));
                await ProductionSeeder.SeedAsync(db, Config(file), new BcryptPasswordHasher(), NullLogger.Instance);
                await DatabaseCompatibility.EnsureAsync(db, nexusBridge: true);
                await ProductionSeeder.SeedAsync(db, Config(file), new BcryptPasswordHasher(), NullLogger.Instance);
                Assert.Equal("独立验收客户", await connection.ExecuteScalarAsync<string>("SELECT name FROM customers WHERE id=42"));
                Assert.Equal(1, await connection.ExecuteScalarAsync<int>("SELECT count(*) FROM \"Users\""));
                Assert.Equal("keep-this-hash", await connection.ExecuteScalarAsync<string>("SELECT \"PasswordHash\" FROM \"Users\" WHERE \"Username\"='historical'"));
            }
            finally { File.Delete(file); }
        });
    }

    [Fact]
    public async Task StandaloneBootstrapStillCreatesItsOriginalDisabledAccount()
    {
        await InDisposableDatabase(async db => {
            await DatabaseCompatibility.EnsureAsync(db);
            var connection = db.Database.GetDbConnection();
            Assert.Equal(ProductionSeeder.DisabledPasswordHash, await connection.ExecuteScalarAsync<string>(
                "SELECT \"PasswordHash\" FROM \"Users\" WHERE \"Username\"='admin'"));
        });
    }

    [Theory]
    [InlineData("nexus-string-id")]
    [InlineData("7")]
    public async Task AuditRetainsNexusIdentityWithoutImpersonatingLegacyIntegerUser(string subject)
    {
        await InDisposableDatabase(async db => {
            await DatabaseCompatibility.EnsureAsync(db, nexusBridge: true);
            var connection = db.Database.GetDbConnection();
            var controller = new TestController { ControllerContext = new ControllerContext {
                HttpContext = new DefaultHttpContext { User = new ClaimsPrincipal(new ClaimsIdentity(new[] {
                    new Claim("nexus_bridge", "1"), new Claim(ClaimTypes.NameIdentifier, subject),
                    new Claim(ClaimTypes.Name, "nexus.employee"), new Claim("nexus_factory", "huadeng"),
                    new Claim("nexus_employment_epoch", "3"), new Claim("nexus_display_name", "现系统人员"),
                }, "nexus-test")) }
            } };
            await controller.WriteAsync(connection, null, "shipments", "update", "shipment", "42", "验收", new { qty = 20 });
            var row = await connection.QuerySingleAsync("SELECT * FROM audit_logs");
            Assert.Null((object?)row.user_id);
            Assert.Equal(subject, (string)row.nexus_user_id);
            Assert.Equal("huadeng", (string)row.nexus_factory_id);
            Assert.Equal("3", (string)row.nexus_employment_epoch);
            Assert.Equal("现系统人员", (string)row.actor_display_name);
            Assert.Equal("nexus.employee", (string)row.username);
            Assert.Contains("20", (string)row.details);
        });
    }

    private sealed class TestController : ControllerBase;
}
