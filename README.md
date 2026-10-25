# GnuCash Read-Only MCP Server

A Python-based Model Context Protocol (MCP) server that exposes a local GnuCash database (MariaDB) as read-only tools for LLMs. 

The goal of this project is to allow local or cloud-based models (via an MCP client like Claude Desktop or a local `llama.cpp` agent) to query personal finance data using natural language, without risking data mutation.

![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![MCP](https://img.shields.io/badge/MCP-stdio-green)

## Architecture

*   **Language:** Python 3.10+
*   **Database:** MariaDB (Raw SQL, no ORM)
*   **Protocol:** Official MCP Python SDK (stdio transport)
*   **LLM Testing:** `llama.cpp` and `promptfoo`

The server exposes a subset of SQL queries as MCP tools. The LLM determines which tool to call and provides the arguments, and the Python server executes the query and returns a JSON envelope.

## Security Model (Read-Only Enforcement)

Because this tool gives an LLM access to a personal database, it uses defense-in-depth to prevent writes:

1.  **Database Level:** The MariaDB user is restricted to `GRANT SELECT` on the specific schema.
2.  **Session Level:** The Python connection explicitly executes `SET SESSION TRANSACTION READ ONLY` and sets a `max_statement_time` before running any query.
3.  **Application Level:** `guard.py` parses the generated SQL, stripping comments and rejecting any statement that is not a `SELECT` or `WITH ... SELECT`. It also blocks file writes (`INTO OUTFILE`) and locking clauses (`FOR UPDATE`).

## Available Tools

The server provides the following tools to the LLM:

| Tool | Description |
|------|-------------|
| `list_accounts` | Returns the account tree with GUIDs, names, and types |
| `get_account_balance` | Calculates the balance of an account and its descendants as of a specific date |
| `get_recent_transactions` | Returns recent transactions for a given account |
| `get_spending_by_category` | Aggregates expenses over a date range |
| `get_income_by_category` | Aggregates income over a date range |
| `search_transactions` | Case-insensitive search across transaction descriptions and memos |
| `get_net_worth` | Calculates total assets minus total liabilities |

## Installation

### Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/gnucash-mcp.git
cd gnucash-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Create .env file (see .env.example)
cp .env.example .env
# Edit .env with your database credentials
```

### Running the Server

```bash
# Start the MCP server
python server.py
```

The server will run on stdio and connect to your MCP client.

### Using with an MCP Client

#### Claude Desktop
Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "gnucash-mcp": {
      "command": "python",
      "args": ["path/to/gnucash-mcp/server.py"],
      "env": {
        "DB_HOST": "127.0.0.1",
        "DB_PORT": "3306",
        "DB_USER": "gnucash_ro",
        "DB_PASSWORD": "your_password",
        "DB_NAME": "gnucash",
        "QUERY_TIMEOUT_S": "10"
      }
    }
  }
}
```

#### llama.cpp / Ollama
Configure your local LLM client to use the stdio transport and point it to the server process.

## Usage Examples

### Query Account Balance
```
"How much money do I have in my EQ Bank account as of 2024-01-15?"
```

### Get Recent Transactions
```
"Show me my last 10 transactions for the Savings account."
```

### Analyze Spending
```
"How much did I spend on groceries in December 2023?"
```

### Get Net Worth
```
"What is my current net worth?"
```

### Search Transactions
```
"Find all transactions related to 'rent' in 2024."
```

## Implementation Notes

**Handling GnuCash Data Formats:**
GnuCash stores currency amounts as integer pairs (`value_num` / `value_denom`). The SQL queries divide these using `CAST(value_num AS DECIMAL) / value_denom` to avoid floating-point inaccuracies.

Dates in GnuCash are stored as `DATETIME` values. The Python helpers convert standard ISO dates (`YYYY-MM-DD`) into the appropriate query bounds.

**Double-Entry Accounting & LLMs:**
GnuCash stores liabilities and income as negative numbers. Small local models often get confused by this when calculating net worth. To fix this, the server splits tools into two categories:
*   *Inspection tools* (like `get_account_balance`) return raw ledger values.
*   *Reporting tools* (like `get_net_worth`) use SQL `ABS()` and explicit JSON keys (e.g., `total_liabilities_owed`) to return human-readable positive values.

## Local LLM Evaluation

To ensure the server works reliably with local models, I set up an evaluation suite using `promptfoo` and `llama-swap`. The tests cover tool routing, argument formatting, and loop prevention.

Models tested include `Qwen3.5-9B`, `LocoOperator-4B`, and `Ling-3B`. You can find the test configurations in the `evals/` directory and the results summary in `docs/evaluation-results.md`.

## Configuration

Create a `.env` file in the project root:

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=gnucash_ro
DB_PASSWORD=your_secure_password
DB_NAME=gnucash
QUERY_TIMEOUT_S=10
```

**Security Warning:** Never commit your `.env` file! Use `.env.example` as a template and add your actual credentials separately.

## Testing

### Unit Tests
```bash
pytest tests/
```

### Smoke Test
```bash
python smoke_test.py "EQ Bank"
```

### Linting
```bash
ruff check .
```

### Full Evaluation
```bash
promptfoo eval
```

## Troubleshooting

### Connection Refused
- Ensure MariaDB is running and accessible
- Verify the database user has `SELECT` permissions
- Check that the database exists and is accessible

### Query Timeout
- Increase `QUERY_TIMEOUT_S` in `.env`
- Check for slow queries in your GnuCash database

### No Matching Account
- Use the full account path (e.g., `Assets:Current Assets:Angie:EQ Bank`)
- Use a substring search (e.g., `EQ Bank`) if the exact path is unknown

### SQL Guard Rejection
- The guard blocks non-SELECT queries for security
- Ensure you're not asking for write operations

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)** - see the [LICENSE](LICENSE) file for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to contribute.

## Security

This project handles sensitive financial data. See [SECURITY.md](SECURITY.md) for security policies and responsible disclosure procedures.

## Architecture

For detailed architecture documentation, see [docs/architecture.md](docs/architecture.md).

## Evaluation Results

See [docs/evaluation-results.md](docs/evaluation-results.md) for LLM performance benchmarks.
