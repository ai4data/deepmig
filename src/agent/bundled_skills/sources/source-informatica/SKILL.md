---
name: source-informatica
description: Informatica PowerCenter/IICS analysis and extraction. Use when config.source.type is "informatica". Parses mappings, sessions, workflows, and maps transformations to target platform equivalents.
allowed-tools: Read, Bash
---

# Informatica Source Skill

## Status: PLACEHOLDER

This skill is planned but not yet fully implemented. The structure below describes the intended capabilities.

## When to Use

Load this skill when the migration config specifies:
```json
{
  "source": {
    "type": "informatica"
  }
}
```

## Planned Capabilities

### 1. Repository Export Parsing
Parse Informatica XML exports:
- Mappings (.xml)
- Sessions (.xml)
- Workflows (.xml)
- Worklets (.xml)

### 2. Transformation Mapping
Map Informatica transformations to target platform equivalents:

| Informatica Component | Target Equivalent |
|-----------------------|-------------------|
| Source Qualifier | Source table read |
| Expression | Column transformation |
| Filter | DataFrame filter |
| Joiner | DataFrame join |
| Lookup | Join or broadcast join |
| Aggregator | groupBy aggregation |
| Sorter | orderBy |
| Router | Filter + Union |
| Union | union |
| Normalizer | explode |
| Rank | window function |
| Sequence Generator | monotonically_increasing_id |

### 3. Mapping Analysis
Extract from mappings:
- Source and target definitions
- Transformation logic
- Expression syntax
- Variable ports

### 4. Workflow Dependencies
Build dependency graph:
- Session dependencies
- Workflow links
- Event-based triggers

## Future Scripts (Not Yet Implemented)

```bash
# Parse Informatica mapping export
python scripts/parse_mapping.py --file "mapping_export.xml"

# Extract all transformations
python scripts/extract_transformations.py --file "mapping_export.xml"

# Build dependency graph
python scripts/build_workflow_graph.py --folder "exports/"
```

## Repository Structure

Informatica exports contain:
```xml
<REPOSITORY>
  <FOLDER>
    <SOURCE/>
    <TARGET/>
    <MAPPING>
      <TRANSFORMATION TYPE="Source Qualifier"/>
      <TRANSFORMATION TYPE="Expression"/>
      <CONNECTOR/>
    </MAPPING>
    <SESSION/>
    <WORKFLOW/>
  </FOLDER>
</REPOSITORY>
```

## Contributing

To implement this skill:
1. Obtain sample Informatica repository exports
2. Create parsers for mapping/session/workflow XML
3. Build transformation mapping engine
4. Generate target platform code from parsed mappings
