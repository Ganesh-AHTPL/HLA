# HLA Studio v3.0 — High-Level Architecture Ingestion & ETL Automation Engine

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Backend](https://img.shields.io/badge/Backend-Flask%20%7C%20SQLAlchemy-red)
![Database](https://img.shields.io/badge/Database-PostgreSQL-336791)
![Frontend](https://img.shields.io/badge/Frontend-React%2018%20%7C%20Vite-61dafb)
![Role](https://img.shields.io/badge/RBAC-Admin%20%7C%20Architect%20%7C%20Viewer-green)

An enterprise-grade orchestration platform that automatically ingests High-Level Architecture (HLA) specifications (`.docx`, `.xlsx`, `.csv`), parses `.kdb` credential vaults, connects upstream to source databases, extracts physical schemas with HLA logic columns alone, and builds complete Target DDL, Transformation SQL, and PySpark pipelines with direct deployment to **Development (Dev)** and **Production (Prod)** target databases.

---

## 1. System Architecture

```mermaid
flowchart TD
    subgraph Ingestion ["1. HLA Specification Ingestion"]
        Doc[Architecture Spec .docx / .xlsx] --> Parser[Document Parser & AST Extractor]
        Parser --> Spec[Data Freshness, Source Systems, Dialects, Truncate vs Append]
    end

    subgraph Vault ["2. Credential Vault & Introspection"]
        KDB[".kdb / .ini / .json / .yaml Vault"] --> VaultParser[Vault Parser & Decryptor]
        VaultParser --> SrcDB[(Source Operational DBs)]
        SrcDB --> Introspect[Live Schema Introspector]
        Introspect --> LogicFilter[Extract HLA Logic Columns Alone]
    end

    subgraph RulesEngine ["3. Pre-Execution & Balance Rules (R1 - R11)"]
        Spec --> Engine[Rules Engine]
        LogicFilter --> Engine
        Engine --> R1_R10["Rules R1–R10: Partitioned Window Deduplication & Filtering"]
        R1_R10 --> R11["Rule R11: CTRL_X_BALANCED_DATASET Gateway"]
    end

    subgraph TargetStudio ["4. Target DB Studio (Dev & Prod)"]
        R11 --> Synth[LLM Target Logic Builder]
        Synth --> DDL["Target DDL (Replicated Source Structure + Logic Columns)"]
        Synth --> SQL["Transformation SQL Script (CTEs + Window Functions)"]
        Synth --> Spark["Production PySpark DataFrame Script"]
        Synth --> Reason["Architectural Reasoning Report"]
    end

    subgraph Deployment ["5. Validation & Live Deployment"]
        DDL --> Validate["Automated Dry-Run Validation (Savepoint Rollback)"]
        Validate --> Deploy["Direct PostgreSQL Deployment"]
        Deploy --> TargetDev[(Target DB: Dev Schema)]
        Deploy --> TargetProd[(Target DB: Prod Schema)]
    end
```

---

## 2. Directory Structure

```text
HLA_Project/
├── app.py                             # Flask API application, route handlers, error handlers
├── models.py                          # SQLAlchemy ORM models (User, Project, Document, DBConnection, TargetArtifact)
├── auth.py                            # JWT authentication, password hashing, RBAC decorators
├── analyzer.py                        # Document ingestion, AST extraction, table/mapping parsing
├── db_fetcher.py                      # Multi-dialect database connector, URL builder, schema discovery
├── vault_parser.py                    # Multi-format credential vault parser (.kdb, .ini, .json, .yaml, .xml)
├── target_logic_builder.py            # Target DDL, Transformation SQL, PySpark generator, dry-run validator & deployer
├── generate_guide_docx.py             # Client specification guide builder (.docx)
├── requirements.txt                   # Backend Python dependencies
├── .env                               # Database credentials and environment variables
│
├── frontend/                          # React + Vite Single Page Application
│   ├── index.html                     # HTML entry point
│   ├── vite.config.js                 # Vite development server configuration & proxy
│   ├── package.json                   # Frontend dependencies and build scripts
│   └── src/
│       ├── main.jsx                   # React root entry point with synchronous JWT initialization
│       ├── App.jsx                    # Core shell, tab navigation, KPI cards, modal routers
│       ├── index.css                  # Enterprise cyber-glass design system & theme tokens
│       └── components/
│           ├── ProjectExplorer.jsx    # Workspaces explorer, search, stats hero, project creator
│           ├── FileUpload.jsx         # HLA document drag-and-drop ingestion & progress terminal
│           ├── DocumentAnalysis.jsx   # Ingestion results, AST lineage, attribute catalog
│           ├── SourceDBManager.jsx    # Named source connection tabs & .kdb vault import
│           ├── TargetDBStudio.jsx     # Target DB Studio (Dev/Prod toggle, code tabs, deploy terminal)
│           ├── GlobalIntrospectModal.jsx # Live database connector & schema inspector
│           ├── RulesModal.jsx         # R1–R10 filter rules & R11 balance test bench
│           ├── LoginModal.jsx         # JWT login & session manager
│           ├── UserManagementModal.jsx # Admin RBAC user provisioning modal
│           ├── RoleInfoModal.jsx      # RBAC permission matrix modal
│           └── TableSchemaModal.jsx   # Column type & nullability inspector
│
└── uploads/                           # Ingested documents & generated artifacts
    └── projects/                      # Project-scoped document storage
```

---

## 3. Data Models & Database Schema

The database uses PostgreSQL managed via SQLAlchemy ORM.

### Entity Relationship Diagram

```mermaid
erDiagram
    User ||--o{ Project : "creates"
    Project ||--o{ Document : "contains"
    Project ||--o{ DBConnection : "configures"
    Project ||--o{ TargetArtifact : "deploys"
    Document ||--o{ TargetArtifact : "generates"

    User {
        int id PK
        string username UK
        string email UK
        string password_hash
        string role "admin | architect | viewer"
        timestamp created_at
    }

    Project {
        int id PK
        string name
        text description
        string folder_path
        int created_by_id FK
        timestamp created_at
    }

    DBConnection {
        int id PK
        int project_id FK
        string source_db_name "e.g. Billing_Warehouse"
        string conn_role "source | target"
        string target_env "none | dev | prod"
        string schema_name "public | target_dev"
        string db_type "postgresql | mysql | snowflake"
        string host
        int port
        string database_name
        string username
        string password
        string connection_string
        string vault_profile
        string status "connected | failed | not_configured"
        timestamp last_tested
    }

    Document {
        int id PK
        int project_id FK
        string filename
        string original_name
        string file_type
        bigint file_size
        string file_path
        string status "uploaded | analyzed | failed"
        json metadata_json
        json analysis_data
        string generated_doc_path
        timestamp uploaded_at
    }

    TargetArtifact {
        int id PK
        int project_id FK
        int document_id FK
        string environment "dev | prod"
        string target_dialect
        string target_schema
        text source_tables_ddl
        text generated_ddl
        text generated_transformation_sql
        text generated_pyspark_code
        json target_schema_json
        text llm_reasoning
        string deployment_status "draft | validated | deployed | failed"
        text deployment_log
        timestamp deployed_at
        timestamp created_at
        timestamp updated_at
    }
```

---

## 4. Complete API Reference

All protected endpoints require `Authorization: Bearer <JWT_TOKEN>` in the HTTP request headers.

### A. Authentication & RBAC

| Method | Endpoint | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/auth/login` | Public | Authenticates credentials and returns JWT token & user profile |
| `GET` | `/api/auth/me` | Logged In | Returns current authenticated user profile and permissions |
| `POST` | `/api/auth/register` | `admin` | Provisions a new user account with assigned role |
| `GET` | `/api/auth/users` | `admin` | Lists all registered users and assigned roles |
| `PUT` | `/api/auth/users/<id>` | `admin` | Updates username, email, password, or role for a user |
| `DELETE` | `/api/auth/users/<id>` | `admin` | Deletes a user account |

### B. Project Workspaces

| Method | Endpoint | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/projects` | Logged In | Lists all workspaces with document and connection counts |
| `POST` | `/api/projects` | `admin`, `architect` | Creates a new isolated project workspace |
| `GET` | `/api/projects/<id>` | Logged In | Retrieves detailed workspace metadata, documents, and connections |
| `DELETE` | `/api/projects/<id>` | `admin`, `architect` | Deletes a workspace and cascades all documents, artifacts, and connections |

### C. Document Ingestion & Analysis

| Method | Endpoint | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/projects/<id>/upload` | `admin`, `architect` | Uploads architecture document (`.docx`, `.xlsx`, `.csv`), extracts AST, and analyzes rules |
| `GET` | `/api/documents/<id>` | Logged In | Retrieves full document metadata, parsed source tables, rules, and lineage |
| `GET` | `/api/documents/<id>/download-generated` | Logged In | Downloads the structured Word (`.docx`) version of the ingested architecture |
| `GET` | `/api/download-spec-guide` | Logged In | Downloads the official HLA Client Document Structure Specification Guide |

### D. Credential Vault & Upstream Connections

| Method | Endpoint | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/projects/<id>/upload-vault` | `admin`, `architect` | Ingests `.kdb`, `.ini`, `.json`, `.yaml`, `.xml` vault and auto-provisions connections |
| `POST` | `/api/projects/<id>/connections` | `admin`, `architect` | Saves or updates a named upstream source database connection |
| `POST` | `/api/projects/<id>/connections/test` | `admin`, `architect` | Tests live connectivity against the supplied database configuration |
| `DELETE` | `/api/projects/<id>/connections/<conn_id>` | `admin`, `architect` | Removes a saved database connection |
| `POST` | `/api/projects/<id>/fetch-table-schema` | Logged In | Fetches physical column names, data types, nullability, and sample records |

### E. Target DB Studio (Dev & Prod)

| Method | Endpoint | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/projects/<id>/targets` | Logged In | Retrieves Target DB configurations for both **Dev** and **Prod** environments |
| `POST` | `/api/projects/<id>/targets` | `admin`, `architect` | Saves Target DB credentials, dialect, host, and target schema namespace |
| `POST` | `/api/projects/<id>/targets/vault-upload` | `admin`, `architect` | Uploads `.kdb` credential vault scoped specifically to target environments |
| `POST` | `/api/documents/<id>/build-target-logic` | `admin`, `architect` | Synthesizes Target DDL, Transformation SQL, and PySpark logic |
| `GET` | `/api/documents/<id>/target-artifacts` | Logged In | Retrieves generated DDL, SQL, PySpark, and deployment history |
| `POST` | `/api/documents/<id>/deploy-target` | `admin`, `architect` | Runs **Dry-Run Validation** (savepoint rollback) or **Live Deployment** to target DB |

### F. Business Rules & Introspection

| Method | Endpoint | Role Required | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/rules/catalog` | Logged In | Returns the complete R1–R10 cleansing filter & R11 balance catalog |
| `POST` | `/api/rules/simulate` | Logged In | Interactive test bench: runs test payload against rules and returns output |
| `POST` | `/api/introspect/global` | Logged In | Introspects multiple database connections simultaneously and reports readiness |

---

## 5. Role-Based Access Control (RBAC)

| Capability | Admin | Architect | Viewer |
| :--- | :---: | :---: | :---: |
| View Workspaces, Documents & Lineage | ✓ | ✓ | ✓ |
| View Target DDL, Transformation SQL, PySpark | ✓ | ✓ | ✓ |
| Inspect Rules Catalog & Test Bench | ✓ | ✓ | ✓ |
| Create Workspaces & Ingest Documents | ✓ | ✓ | — |
| Upload `.kdb` Credential Vaults | ✓ | ✓ | — |
| Build Target Logic with LLM | ✓ | ✓ | — |
| Validate & Deploy to Target DBs | ✓ | ✓ | — |
| User Provisioning & Role Management | ✓ | — | — |

---

## 6. Installation & Run Guide

### Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: 18.0 or higher
- **PostgreSQL**: 14, 15, 16, or 17 (local or remote)

### Step 1: Clone & Configure Environment

```bash
git clone <repository_url>
cd HLA_Project
```

Create or verify the root `.env` file:
```env
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/hla_db
SECRET_KEY=your_jwt_secret_key_here
FLASK_ENV=development
```

### Step 2: Set Up Backend

```bash
# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the Flask backend server (defaults to port 5000)
python app.py
```

On first start, `app.py` will automatically:
1. Connect to PostgreSQL and create all tables (`users`, `projects`, `documents`, `db_connections`, `target_artifacts`).
2. Seed default users:
   - **Admin**: `admin` / `admin123`
   - **Architect**: `architect` / `arch123`
   - **Viewer**: `viewer` / `viewer123`

### Step 3: Set Up Frontend

```bash
cd frontend

# Install npm dependencies
npm install

# Start the Vite development server (port 3000)
npm run dev
```

Open `http://localhost:3000` in your web browser.

---

## 7. End-to-End Workflow Guide

1. **Log In**:
   - Sign in using `admin` / `admin123` or `architect` / `arch123`.
2. **Create a Workspace**:
   - Click **`+ New Workspace`**, enter a project name (e.g. `Billing_Reconciliation`), and submit.
3. **Ingest HLA Document**:
   - Drag and drop your `.docx` or `.xlsx` architecture specification file.
   - The engine automatically scans and extracts source systems, refresh schedules, pre-execution rules (R1–R10), R11 balance node, and attribute derivations.
4. **Configure Database Credentials**:
   - Go to **Database Connectors** or upload a `.kdb` credential vault file.
   - The system connects upstream, verifies connectivity, and introspects physical column names and types.
5. **Open Target DB Studio**:
   - Switch to the **Target DB Studio (Dev / Prod)** tab.
   - Select your target environment: **Development (DEV)** or **Production (PROD)**.
   - Configure target database credentials (host, port, database name, username, password).
6. **Synthesize Target Logic**:
   - Click **`⚡ Build Target Logic with LLM`**.
   - The engine synthesizes:
     - **Target DDL**: Creates target tables taking the exact structure from the source with HLA logic columns alone.
     - **Transformation SQL**: Full CTE-based SQL implementing R1–R10 filtering and R11 balance dataset staging.
     - **PySpark Script**: Scalable enterprise PySpark ETL pipeline.
7. **Validate & Deploy**:
   - Click **`🧪 Validate & Dry-Run`** to test DDL syntax inside an isolated rollback transaction.
   - Click **`🚀 Deploy to Target DB`** to provision the schemas and tables directly into your database.
