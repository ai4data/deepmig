# DeepMig Sandbox Strategy

A strategic document outlining the role of sandboxes in making DeepMig a world-class migration platform.

## Executive Summary

Sandboxes are isolated, ephemeral execution environments that enable DeepMig to safely generate, test, and deploy migration code at scale. They are **indispensable** for:

- Safe code execution before production deployment
- Multi-customer isolation in a SaaS model
- Parallel migration wave execution
- Long-running operations without blocking users
- Reproducible, auditable migration processes

---

## Why Sandboxes Are Critical

### The Problem Without Sandboxes

```
AI Agent generates code → Runs directly on production
                              │
                              ▼
                         HIGH RISK
                    - Untested code
                    - No rollback
                    - Customer data exposure
                    - Resource conflicts
```

### The Solution With Sandboxes

```
AI Agent generates code → Sandbox (test/validate) → Production
                              │
                              ▼
                         LOW RISK
                    - Code validated
                    - Errors caught early
                    - Isolated execution
                    - Safe iteration
```

---

## Core Use Cases

### 1. Code Generation & Validation

**Scenario:** DeepMig agent generates a PySpark transformation script.

```
┌─────────────────────────────────────────────────────────────────┐
│                    CODE VALIDATION PIPELINE                      │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Generate │───►│ Syntax   │───►│ Test     │───►│ Deploy   │  │
│  │ Code     │    │ Check    │    │ Execute  │    │ to Prod  │  │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘  │
│                        │              │                         │
│                        │   SANDBOX    │                         │
│                        └──────────────┘                         │
│                                                                  │
│  Catches:                                                        │
│  ✗ Syntax errors          ✗ Type mismatches                     │
│  ✗ Missing dependencies   ✗ Logic bugs                          │
│  ✗ Performance issues     ✗ Data quality problems               │
└─────────────────────────────────────────────────────────────────┘
```

**Without sandbox:** Bugs discovered in production, causing downtime and data issues.

**With sandbox:** Bugs caught before deployment, agent can self-correct.

---

### 2. Multi-Tenant Customer Isolation

**Scenario:** DeepMig as SaaS serving multiple enterprise customers.

```
┌─────────────────────────────────────────────────────────────────┐
│                     DEEPMIG SAAS PLATFORM                        │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  CUSTOMER A     │  │  CUSTOMER B     │  │  CUSTOMER C     │  │
│  │  (Healthcare)   │  │  (Finance)      │  │  (Retail)       │  │
│  │                 │  │                 │  │                 │  │
│  │  ┌───────────┐  │  │  ┌───────────┐  │  │  ┌───────────┐  │  │
│  │  │ Sandbox A │  │  │  │ Sandbox B │  │  │  │ Sandbox C │  │  │
│  │  │           │  │  │  │           │  │  │  │           │  │  │
│  │  │ - HIPAA   │  │  │  │ - SOX     │  │  │  │ - PCI     │  │  │
│  │  │ - PHI data│  │  │  │ - PII data│  │  │  │ - Card    │  │  │
│  │  │           │  │  │  │           │  │  │  │   data    │  │  │
│  │  └───────────┘  │  │  └───────────┘  │  │  └───────────┘  │  │
│  │                 │  │                 │  │                 │  │
│  │  ISOLATED       │  │  ISOLATED       │  │  ISOLATED       │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
│  Guarantees:                                                     │
│  ✓ No data leakage between customers                            │
│  ✓ Compliance boundaries respected                              │
│  ✓ Independent scaling per customer                             │
│  ✓ Customer-specific configurations                             │
└─────────────────────────────────────────────────────────────────┘
```

**Critical for:** Enterprise sales, compliance certifications (SOC2, HIPAA, GDPR).

---

### 3. Parallel Migration Waves

**Scenario:** Large migration with 500 tables, 200 ETL jobs.

```
┌─────────────────────────────────────────────────────────────────┐
│                   PARALLEL WAVE EXECUTION                        │
│                                                                  │
│  Traditional (Sequential):                                       │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                       │
│  │ T1  │→│ T2  │→│ T3  │→│ ... │→│T500 │  = 50 hours           │
│  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘                       │
│                                                                  │
│  With Sandboxes (Parallel):                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │ Sandbox 1   │ │ Sandbox 2   │ │ Sandbox 3   │                │
│  │ T1-T100     │ │ T101-T200   │ │ T201-T300   │  ...           │
│  │             │ │             │ │             │                │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘                │
│         │               │               │                        │
│         └───────────────┼───────────────┘                        │
│                         ▼                                        │
│                    = 5 hours (10x faster)                        │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits:**
- 10x faster migration completion
- Independent failure domains (one wave fails, others continue)
- Resource optimization per wave

---

### 4. Target Environment Simulation

**Scenario:** Validate migration before touching production Databricks.

```
┌─────────────────────────────────────────────────────────────────┐
│                 ENVIRONMENT SIMULATION                           │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    SIMULATION SANDBOX                      │  │
│  │                                                            │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │  │
│  │  │ Spark 3.5    │  │ Unity        │  │ Delta Lake   │    │  │
│  │  │ Runtime      │  │ Catalog      │  │ 3.0          │    │  │
│  │  │              │  │ (mock)       │  │              │    │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘    │  │
│  │                                                            │  │
│  │  Test Data: 1% sample of production                        │  │
│  │                                                            │  │
│  │  Validates:                                                │  │
│  │  ✓ Schema compatibility                                    │  │
│  │  ✓ Data type mappings (SQL Server → Delta)                │  │
│  │  ✓ Transformation correctness                              │  │
│  │  ✓ Query performance estimates                             │  │
│  │  ✓ Storage requirements                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│                    PRODUCTION DATABRICKS                         │
│                    (deploy with confidence)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

### 5. Self-Healing Agent Loop

**Scenario:** Agent encounters error, fixes code, retests in sandbox.

```
┌─────────────────────────────────────────────────────────────────┐
│                    SELF-HEALING LOOP                             │
│                                                                  │
│         ┌──────────────────────────────────────────┐            │
│         │                                          │            │
│         ▼                                          │            │
│  ┌──────────────┐    ┌──────────────┐    ┌────────┴─────┐      │
│  │ Generate     │───►│ Execute in   │───►│ Error?       │      │
│  │ Code         │    │ Sandbox      │    │              │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│                                                 │ Yes           │
│                                                 ▼               │
│                                          ┌──────────────┐       │
│                                          │ Analyze      │       │
│                                          │ Error        │       │
│                                          └──────┬───────┘       │
│                                                 │               │
│                                                 ▼               │
│                                          ┌──────────────┐       │
│                                          │ Fix Code     │───────┘
│                                          │ (Agent)      │  Retry
│                                          └──────────────┘       │
│                                                                  │
│  Example:                                                        │
│  1. Agent generates: df.select("CustomerID")                    │
│  2. Sandbox error: Column 'CustomerID' not found                │
│  3. Agent analyzes: Schema has 'customer_id' (lowercase)        │
│  4. Agent fixes: df.select("customer_id")                       │
│  5. Sandbox: Success!                                           │
│  6. Deploy to production                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

### 6. Long-Running Async Operations

**Scenario:** Migration takes 8 hours, user shouldn't wait.

```
┌─────────────────────────────────────────────────────────────────┐
│                  ASYNC EXECUTION MODEL                           │
│                                                                  │
│  User's Machine                Cloud Sandbox                     │
│  ┌──────────────┐             ┌──────────────┐                  │
│  │ DeepMig CLI  │────────────►│ Migration    │                  │
│  │              │  "Start     │ Running...   │                  │
│  │ > deepmig    │   migration"│              │                  │
│  │   migrate    │             │ Hour 1: 12%  │                  │
│  │   --async    │             │ Hour 2: 25%  │                  │
│  │              │             │ Hour 3: 37%  │                  │
│  │ Migration    │             │ ...          │                  │
│  │ started!     │             │ Hour 8: 100% │                  │
│  │ ID: abc-123  │             │              │                  │
│  │              │◄────────────│ COMPLETE     │                  │
│  │ (user can    │  Webhook/   │              │                  │
│  │  close CLI)  │  Email      │              │                  │
│  └──────────────┘             └──────────────┘                  │
│                                                                  │
│  User can:                                                       │
│  - Close laptop                                                  │
│  - Check status anytime: deepmig status abc-123                 │
│  - Get notified on completion (email, Slack, webhook)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DEEPMIG PLATFORM                                    │
│                                                                                  │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                            CONTROL PLANE                                   │  │
│  │                                                                            │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐          │  │
│  │  │ API        │  │ Agent      │  │ Sandbox    │  │ Job        │          │  │
│  │  │ Gateway    │  │ Manager    │  │ Controller │  │ Scheduler  │          │  │
│  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘          │  │
│  │        │               │               │               │                  │  │
│  │        └───────────────┴───────────────┴───────────────┘                  │  │
│  │                                │                                           │  │
│  └────────────────────────────────┼───────────────────────────────────────────┘  │
│                                   │                                              │
│                                   ▼                                              │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                           SANDBOX POOL                                     │  │
│  │                                                                            │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │                        SANDBOX TYPES                                 │  │  │
│  │  │                                                                      │  │  │
│  │  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │  │  │
│  │  │  │ CODE TEST  │  │ TRANSFORM  │  │ VALIDATION │  │ DEPLOYMENT │    │  │  │
│  │  │  │            │  │            │  │            │  │            │    │  │  │
│  │  │  │ - Syntax   │  │ - Spark    │  │ - Data     │  │ - Dry run  │    │  │  │
│  │  │  │ - Lint     │  │ - pandas   │  │   quality  │  │ - Rollback │    │  │  │
│  │  │  │ - Unit     │  │ - DBT      │  │ - Schema   │  │ - Atomic   │    │  │  │
│  │  │  │   tests    │  │            │  │   match    │  │            │    │  │  │
│  │  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │  │  │
│  │  │                                                                      │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                            │  │
│  │  Lifecycle: Create (seconds) → Execute → Capture Results → Destroy        │  │
│  │                                                                            │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Sandbox Lifecycle

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ REQUEST │────►│ PROVISION│────►│ EXECUTE │────►│ CAPTURE │────►│ DESTROY │
└─────────┘     └─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │               │
     ▼               ▼               ▼               ▼               ▼
  Agent          Spin up VM      Run code       Save logs,       Clean up
  requests       or container    or script      artifacts,       resources
  sandbox        (2-10 sec)                     results
```

### Integration Points

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEEPMIG AGENT                                 │
│                                                                  │
│  async def run_migration_step(self, code: str):                 │
│      # 1. Request sandbox                                        │
│      sandbox = await self.sandbox_controller.create(             │
│          type="transform",                                       │
│          runtime="spark-3.5",                                    │
│          timeout=3600                                            │
│      )                                                           │
│                                                                  │
│      # 2. Execute code                                           │
│      result = await sandbox.execute(code)                        │
│                                                                  │
│      # 3. Handle result                                          │
│      if result.success:                                          │
│          return result.output                                    │
│      else:                                                       │
│          # Self-heal: analyze error, fix code, retry             │
│          fixed_code = await self.fix_code(code, result.error)    │
│          return await self.run_migration_step(fixed_code)        │
│                                                                  │
│      # 4. Sandbox auto-destroyed after execution                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Provider Comparison

| Provider | Spin-up Time | AI-Native | Spark Support | Cost Model | Best For |
|----------|--------------|-----------|---------------|------------|----------|
| **E2B** | ~2 sec | Yes | Via install | Per-second | AI agent code execution |
| **Modal** | ~1 sec | Yes | Yes | Per-second | Python/ML workloads |
| **Fly.io** | ~3 sec | No | Via Docker | Per-second | Global distribution |
| **AWS Fargate** | ~30 sec | No | Via EMR | Per-second | AWS-native enterprises |
| **Azure Container Instances** | ~20 sec | No | Via Synapse | Per-second | Azure-native (Databricks) |
| **Databricks Jobs** | ~60 sec | No | Native | Per-DBU | Spark-heavy workloads |

### Recommended Stack

```
┌─────────────────────────────────────────────────────────────────┐
│                    RECOMMENDED SETUP                             │
│                                                                  │
│  Development / POC:                                              │
│  └── E2B (fast, AI-native, simple SDK)                          │
│                                                                  │
│  Production (Azure customers):                                   │
│  └── Azure Container Instances + Databricks Jobs                │
│                                                                  │
│  Production (AWS customers):                                     │
│  └── AWS Fargate + EMR Serverless                               │
│                                                                  │
│  Production (Multi-cloud):                                       │
│  └── Modal (cloud-agnostic, fast, Python-native)                │
└─────────────────────────────────────────────────────────────────┘
```

### Spark-Specific Sandbox Options

Most AI sandbox providers (E2B, Modal) don't have native Apache Spark support. For Spark workloads, use a **hybrid approach**:

```
┌─────────────────────────────────────────────────────────────────┐
│              SPARK SANDBOX STRATEGY (HYBRID)                     │
│                                                                  │
│  STAGE 1: Code Validation          STAGE 2: Spark Execution     │
│  ┌──────────────────────┐          ┌──────────────────────┐    │
│  │ E2B / Modal          │          │ Cloud Spark Service  │    │
│  │                      │          │                      │    │
│  │ • Syntax checking    │   ───►   │ • Databricks         │    │
│  │ • Unit tests         │  Deploy  │   Serverless         │    │
│  │ • Schema validation  │          │ • EMR Serverless     │    │
│  │ • PySpark local mode │          │ • Dataproc Serverless│    │
│  │                      │          │                      │    │
│  │ Fast: 2-5 seconds    │          │ Start: 30-60 seconds │    │
│  │ Cost: ~$0.001/run    │          │ Cost: ~$0.10+/run    │    │
│  └──────────────────────┘          └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

| Provider | Type | Spark Support | Startup Time | Best For |
|----------|------|---------------|--------------|----------|
| **E2B** | AI Sandbox | PySpark local (pip install) | ~2 sec | Code validation |
| **Modal** | AI Sandbox | Custom Spark image | ~1 sec | Python/ML |
| **Databricks Serverless** | Spark-native | Full Spark cluster | ~30 sec | Production jobs |
| **AWS EMR Serverless** | Spark-native | Full Spark cluster | ~60 sec | AWS workloads |
| **Dataproc Serverless** | Spark-native | Full Spark cluster | ~45 sec | GCP workloads |
| **Azure Synapse Serverless** | Spark-native | Spark pools | ~60 sec | Azure workloads |

**Recommended for DeepMig:**
1. **Validation phase**: E2B with PySpark local mode (fast, cheap)
2. **Execution phase**: Databricks Serverless Jobs API (native Spark, production-ready)

```python
# Example: Hybrid validation + execution
async def validate_and_execute(code: str, target_table: str):
    # Stage 1: Quick validation in E2B
    sandbox = e2b.Sandbox()
    validation = await sandbox.run(f"""
        pip install pyspark
        python -c '''
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.master("local[*]").getOrCreate()
        # Validate syntax and basic logic
        {code}
        '''
    """)

    if validation.error:
        return {"status": "validation_failed", "error": validation.error}

    # Stage 2: Execute on Databricks Serverless
    dbx_client = WorkspaceClient()
    run = dbx_client.jobs.submit(
        run_name=f"deepmig-{target_table}",
        tasks=[{
            "task_key": "migrate",
            "spark_python_task": {"python_file": f"dbfs:/deepmig/{target_table}.py"}
        }]
    )

    return {"status": "submitted", "run_id": run.run_id}
```

---

## Implementation Roadmap

### Phase 1: Foundation (Current + 2 weeks)
- [ ] Local CLI with push pattern (DONE)
- [ ] Basic code generation (DONE)
- [ ] Manual validation by user

### Phase 2: Code Validation Sandbox (+ 4 weeks)
- [ ] Integrate E2B for code testing
- [ ] Syntax and lint checking in sandbox
- [ ] Unit test execution
- [ ] Error capture and agent feedback loop

### Phase 3: Transform Sandbox (+ 6 weeks)
- [ ] Spark runtime in sandbox
- [ ] Sample data execution
- [ ] Performance profiling
- [ ] Schema validation

### Phase 4: Multi-Tenant Isolation (+ 8 weeks)
- [ ] Customer-specific sandbox pools
- [ ] Credential isolation
- [ ] Audit logging per tenant
- [ ] Compliance boundaries

### Phase 5: Parallel Execution (+ 10 weeks)
- [ ] Wave-based sandbox orchestration
- [ ] Resource optimization
- [ ] Progress aggregation
- [ ] Failure handling per wave

### Phase 6: Production Hardening (+ 12 weeks)
- [ ] Auto-scaling sandbox pools
- [ ] Cost optimization
- [ ] SLA monitoring
- [ ] Disaster recovery

---

## Security Considerations

### Credential Management

```
┌─────────────────────────────────────────────────────────────────┐
│                 CREDENTIAL FLOW                                  │
│                                                                  │
│  ┌────────────┐     ┌────────────┐     ┌────────────┐          │
│  │ Customer   │     │ DeepMig    │     │ Sandbox    │          │
│  │ Vault      │────►│ Secret     │────►│ (runtime   │          │
│  │ (KeyVault) │     │ Manager    │     │  injection)│          │
│  └────────────┘     └────────────┘     └────────────┘          │
│                                                                  │
│  Principles:                                                     │
│  ✓ Secrets never stored in DeepMig database                     │
│  ✓ Short-lived tokens (1 hour max)                              │
│  ✓ Injected at runtime, not baked into sandbox                  │
│  ✓ Audit log of all secret access                               │
└─────────────────────────────────────────────────────────────────┘
```

### Network Isolation

```
┌─────────────────────────────────────────────────────────────────┐
│                 NETWORK BOUNDARIES                               │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    SANDBOX                               │    │
│  │                                                          │    │
│  │  Allowed:                     Blocked:                   │    │
│  │  ✓ Databricks workspace       ✗ Other customer sandboxes │    │
│  │  ✓ Customer cloud storage     ✗ DeepMig internal APIs    │    │
│  │  ✓ Specific egress IPs        ✗ Internet (default)       │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Audit & Compliance

| Event | Logged Data | Retention |
|-------|-------------|-----------|
| Sandbox created | Customer, type, timestamp | 1 year |
| Code executed | Hash of code, duration, result | 1 year |
| Secret accessed | Secret name (not value), accessor | 7 years |
| Data processed | Row counts, table names | 1 year |
| Sandbox destroyed | Duration, resources used | 90 days |

---

## Cost Model

### Sandbox Costs (Estimated)

| Sandbox Type | Duration | Compute | Storage | Total/Run |
|--------------|----------|---------|---------|-----------|
| Code Test | 30 sec | $0.001 | $0.000 | ~$0.001 |
| Transform (small) | 5 min | $0.02 | $0.001 | ~$0.02 |
| Transform (large) | 30 min | $0.15 | $0.01 | ~$0.16 |
| Full validation | 1 hour | $0.30 | $0.02 | ~$0.32 |

### Example Migration Cost

```
Migration: 100 tables, 50 ETL jobs

Sandbox Usage:
- Code tests:     150 runs × $0.001  = $0.15
- Transforms:     100 runs × $0.02   = $2.00
- Validations:     50 runs × $0.32   = $16.00
- Retries (20%):   60 runs × $0.05   = $3.00
                                      ────────
Total sandbox cost:                   ~$21.15

vs. Manual testing cost:              ~$5,000+ (engineer time)
```

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Sandbox spin-up time | < 5 seconds | P95 latency |
| Code validation accuracy | > 95% | Bugs caught before prod |
| Self-heal success rate | > 80% | Auto-fixed errors |
| Customer isolation | 100% | Zero cross-tenant access |
| Cost per migration | < $50 | Sandbox + compute |

---

## Conclusion

Sandboxes transform DeepMig from a code generator into a **trusted, enterprise-ready migration platform**. They enable:

1. **Safety** - Test before deploy, catch errors early
2. **Scale** - Parallel execution, multi-tenant isolation
3. **Autonomy** - Self-healing agents that iterate without human intervention
4. **Trust** - Auditable, reproducible migrations

The investment in sandbox infrastructure pays off through faster migrations, fewer production incidents, and enterprise customer confidence.
