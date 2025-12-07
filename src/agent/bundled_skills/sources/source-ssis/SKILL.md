---
name: source-ssis
description: SSIS package analysis and extraction. Use when config.source.type is "ssis". Parses DTSX packages, extracts data flows, control flows, and maps transformations to target platform equivalents.
allowed-tools: Read, Bash
---

# SSIS Source Skill

## Status: PLACEHOLDER

This skill is planned but not yet fully implemented. The structure below describes the intended capabilities.

## When to Use

Load this skill when the migration config specifies:
```json
{
  "source": {
    "type": "ssis"
  }
}
```

## Planned Capabilities

### 1. Package Parsing
Parse .dtsx package files to extract:
- Control Flow tasks
- Data Flow components
- Connection managers
- Variables and parameters

### 2. Transformation Mapping
Map SSIS transformations to target platform equivalents:

| SSIS Component | Target Equivalent |
|----------------|-------------------|
| OLE DB Source | JDBC/Spark source |
| Derived Column | DataFrame transform |
| Lookup | Join operation |
| Conditional Split | Filter/When clause |
| Sort | orderBy |
| Aggregate | groupBy |
| Merge Join | join |
| Union All | union |

### 3. Dependency Analysis
Build dependency graph of packages:
- Execute Package tasks
- Precedence constraints
- Data flow dependencies

## Future Scripts (Not Yet Implemented)

```bash
# Parse DTSX package
python scripts/parse_dtsx.py --package "path/to/package.dtsx"

# Extract data flows
python scripts/extract_dataflows.py --package "path/to/package.dtsx"

# Generate dependency graph
python scripts/build_dependency_graph.py --folder "path/to/ssis/project"
```

## Implementation Notes

DTSX files are XML-based. Key namespaces:
- `DTS` - Data Transformation Services elements
- `SQLDTS` - SQL Server specific elements

Package structure:
```xml
<DTS:Executable>
  <DTS:ConnectionManagers/>
  <DTS:Variables/>
  <DTS:Executables>  <!-- Control Flow -->
    <DTS:Executable>  <!-- Data Flow Task -->
      <pipeline>  <!-- Data Flow components -->
      </pipeline>
    </DTS:Executable>
  </DTS:Executables>
</DTS:Executable>
```

## Contributing

To implement this skill:
1. Create `scripts/parse_dtsx.py` using Python's xml.etree
2. Map SSIS DTS namespaces to parsed objects
3. Build transformation mapping logic
4. Test with sample SSIS packages
