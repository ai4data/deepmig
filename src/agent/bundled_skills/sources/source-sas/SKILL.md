---
name: source-sas
description: SAS code analysis and extraction. Use when config.source.type is "sas". Parses SAS programs, DATA steps, PROC steps, and maps to target platform equivalents (PySpark, SQL).
allowed-tools: Read, Bash
---

# SAS Source Skill

## Status: PLACEHOLDER

This skill is planned but not yet fully implemented. The structure below describes the intended capabilities.

## When to Use

Load this skill when the migration config specifies:
```json
{
  "source": {
    "type": "sas"
  }
}
```

## Planned Capabilities

### 1. SAS Program Parsing
Parse SAS programs to extract:
- DATA steps
- PROC steps
- Macro definitions
- Library references

### 2. DATA Step Translation
Map SAS DATA step operations to target equivalents:

| SAS DATA Step | Target Equivalent |
|---------------|-------------------|
| `SET` | Read DataFrame |
| `MERGE` | DataFrame join |
| `IF-THEN-ELSE` | when/otherwise |
| `DO-END` | Loop logic |
| `OUTPUT` | Write row |
| `RETAIN` | Window function |
| `ARRAY` | Array operations |
| `BY` | Group operations |
| `WHERE` | filter |
| `KEEP/DROP` | select columns |

### 3. PROC Translation
Map SAS PROCs to target equivalents:

| SAS PROC | Target Equivalent |
|----------|-------------------|
| `PROC SQL` | Spark SQL |
| `PROC SORT` | orderBy |
| `PROC MEANS` | groupBy + agg |
| `PROC FREQ` | groupBy + count |
| `PROC TRANSPOSE` | pivot |
| `PROC APPEND` | union |
| `PROC DATASETS` | Table operations |

### 4. Macro Analysis
Parse and expand SAS macros:
- `%MACRO` definitions
- `%LET` variables
- `%DO` loops
- Macro parameters

## Future Scripts (Not Yet Implemented)

```bash
# Parse SAS program
python scripts/parse_sas.py --file "program.sas"

# Extract DATA steps
python scripts/extract_data_steps.py --file "program.sas"

# Translate to PySpark
python scripts/translate_to_pyspark.py --file "program.sas"
```

## SAS Program Structure

```sas
/* Library references */
LIBNAME mylib '/path/to/data';

/* DATA step */
DATA output_table;
    SET input_table;
    WHERE status = 'ACTIVE';
    new_col = old_col * 2;
RUN;

/* PROC step */
PROC SQL;
    CREATE TABLE result AS
    SELECT * FROM table1 a
    LEFT JOIN table2 b ON a.id = b.id;
QUIT;
```

## Translation Challenges

1. **RETAIN Statement**: Requires window functions or stateful processing
2. **First./Last. Variables**: Map to row_number() partitions
3. **Macro Variables**: Expand or convert to parameters
4. **Implicit Loops**: DATA step implicit iteration needs explicit loops
5. **Missing Values**: SAS handles missing differently than Spark

## Contributing

To implement this skill:
1. Create SAS parser (consider using saspy or antlr4)
2. Build AST for DATA and PROC steps
3. Create translation rules for each construct
4. Handle macro expansion
5. Test with real SAS programs
