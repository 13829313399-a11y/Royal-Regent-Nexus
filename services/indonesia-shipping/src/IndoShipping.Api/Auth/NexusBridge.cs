using System.Data;
using System.Security.Cryptography;
using System.Text;
using Dapper;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using IndoShipping.Infrastructure.Persistence;

namespace IndoShipping.Api.Auth;

/// <summary>A bridge instance owns exactly one dedicated PostgreSQL database.</summary>
public static class NexusBridge
{
    public static readonly HashSet<string> Factories = new(StringComparer.Ordinal)
        { "huakang-a", "huakang-b", "huakang-c", "huakang-d", "huadeng", "huaxing" };

    public static async Task BindDatabaseAsync(AppDbContext db, string factory, bool adoptExisting)
    {
        var connection = db.Database.GetDbConnection();
        if (connection.State != ConnectionState.Open) await connection.OpenAsync();
        // The binding lives in public, independent of the configured business schema.
        // Serialize first startup so two factories cannot simultaneously claim a DB.
        await using var tx = await connection.BeginTransactionAsync();
        await connection.ExecuteAsync("SELECT pg_advisory_xact_lock(8301741109)", transaction: tx);
        var exists = await connection.ExecuteScalarAsync<bool>(
            "SELECT to_regclass('public.nexus_indonesia_factory_binding') IS NOT NULL", transaction: tx);
        if (!exists)
        {
            var hasTables = await connection.ExecuteScalarAsync<bool>("""
                SELECT EXISTS(SELECT 1 FROM information_schema.tables
                  WHERE table_schema NOT IN ('pg_catalog', 'information_schema') AND table_type='BASE TABLE')
                """, transaction: tx);
            if (hasTables && !adoptExisting)
                throw new InvalidOperationException("Existing database requires verified backup and explicit NexusBridge:AdoptExistingDatabase=true");
            await connection.ExecuteAsync("""
                CREATE TABLE public.nexus_indonesia_factory_binding(
                    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), factory_id text NOT NULL);
                """, transaction: tx);
        }
        await connection.ExecuteAsync("""
            INSERT INTO public.nexus_indonesia_factory_binding(singleton, factory_id)
            VALUES(true, @factory) ON CONFLICT(singleton) DO NOTHING
            """, new { factory }, tx);
        var bound = await connection.ExecuteScalarAsync<string>(
            "SELECT factory_id FROM public.nexus_indonesia_factory_binding WHERE singleton=true", transaction: tx);
        if (bound != factory) throw new InvalidOperationException("Database belongs to another Nexus factory; startup refused");
        await tx.CommitAsync();
    }
}
