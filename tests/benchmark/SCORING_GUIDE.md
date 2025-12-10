# BENCHMARK SCORING GUIDE
# =======================
# 
# This document tracks the seeded bugs and InspectAI's detection performance.
# Run the InspectAI commands on the PR and fill in the results below.

## Seeded Bugs Summary

| File | Total Bugs | Security | Logic | Resource | Concurrency | Error Handling |
|------|------------|----------|-------|----------|-------------|----------------|
| seeded_bugs_python.py | 15 | 5 | 7 | 1 | 1 | 1 |
| seeded_bugs_api.py | 12 | 7 | 4 | 0 | 1 | 0 |
| **TOTAL** | **27** | **12** | **11** | **1** | **2** | **1** |

---

## Detailed Bug List (Ground Truth)

### File 1: seeded_bugs_python.py

| # | Bug Type | Severity | Category | Line | Description |
|---|----------|----------|----------|------|-------------|
| 1 | SQL Injection | HIGH | Security | 31 | User input directly in SQL query |
| 2 | Hardcoded Secret | CRITICAL | Security | 41-42 | API key and password in source |
| 3 | Off-by-One | MEDIUM | Logic | 56 | range(len+1) causes IndexError |
| 4 | Missing Null Check | MEDIUM | Logic | 66 | No None check before access |
| 5 | Resource Leak | MEDIUM | Resource | 76 | File never closed |
| 6 | Wrong Operator | HIGH | Logic | 86 | Using 'is' instead of '==' |
| 7 | Wrong Formula | LOW | Logic | 99 | Dividing by (n-1) not n |
| 8 | Race Condition | HIGH | Concurrency | 107 | Non-atomic counter increment |
| 9 | XSS | HIGH | Security | 118 | Unescaped user input in HTML |
| 10 | Weak Crypto | CRITICAL | Security | 131 | MD5 for password hashing |
| 11 | Missing Return | MEDIUM | Logic | 141 | No return True for valid case |
| 12 | Mutable Default | MEDIUM | Logic | 152 | Default arg `[]` persists |
| 13 | Unhandled Exception | MEDIUM | Error | 160 | No try-except for json.loads |
| 14 | Path Traversal | HIGH | Security | 168 | User can access any file |
| 15 | Infinite Loop | HIGH | Logic | 181 | Binary search doesn't converge |

### File 2: seeded_bugs_api.py

| # | Bug Type | Severity | Category | Line | Description |
|---|----------|----------|----------|------|-------------|
| 16 | Command Injection | CRITICAL | Security | 29 | shell=True with user input |
| 17 | Insecure Deserialize | CRITICAL | Security | 41 | pickle.loads on untrusted data |
| 18 | Weak Session | HIGH | Security | 51 | Predictable session tokens |
| 19 | Missing AuthZ | HIGH | Security | 62 | No permission check for delete |
| 20 | ReDoS | MEDIUM | Security | 74 | Evil regex pattern |
| 21 | Float Comparison | MEDIUM | Logic | 88 | Using == for floats |
| 22 | TOCTOU | HIGH | Concurrency | 96 | Check-then-use race condition |
| 23 | Precision Loss | MEDIUM | Logic | 105 | int() truncates cents |
| 24 | Weak Regex | LOW | Logic | 116 | Email regex too permissive |
| 25 | Type Confusion | MEDIUM | Logic | 123 | No type validation before divide |
| 26 | Timing Attack | MEDIUM | Security | 126 | String compare short-circuits |
| 27 | Info Disclosure | LOW | Security | 137 | Error reveals username exists |

---

## Testing Procedure

1. Open PR from `test-benchmark` branch to `main`
2. Run these commands and record findings:

### Command 1: `/inspectai_review`
- [ ] Run command
- Findings count: ___
- True Positives: ___
- False Positives: ___

### Command 2: `/inspectai_bugs`  
- [ ] Run command
- Findings count: ___
- True Positives: ___
- False Positives: ___

### Command 3: `/inspectai_security`
- [ ] Run command
- Findings count: ___
- True Positives: ___
- False Positives: ___

---

## Scoring Template

After running commands, fill in this table:

| Command | Bugs Found | True Positives | False Positives | Recall | Precision |
|---------|------------|----------------|-----------------|--------|-----------|
| /inspectai_review | | | | | |
| /inspectai_bugs | | | | | |
| /inspectai_security | | | | | |

### Formulas:
- **Recall** = True Positives / Total Seeded Bugs (27)
- **Precision** = True Positives / (True Positives + False Positives)
- **F1 Score** = 2 × (Precision × Recall) / (Precision + Recall)

---

## Categories Breakdown (After Testing)

| Category | Total | Found | Recall |
|----------|-------|-------|--------|
| Security (CRITICAL) | 4 | | |
| Security (HIGH) | 5 | | |
| Security (MEDIUM) | 3 | | |
| Security (LOW) | 1 | | |
| Logic Errors | 11 | | |
| Resource Leaks | 1 | | |
| Concurrency | 2 | | |
| Error Handling | 1 | | |

---

## Notes
<!-- Record any observations during testing -->

