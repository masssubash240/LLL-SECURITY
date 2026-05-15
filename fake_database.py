"""
Fake SQLite banking ledger for cybersecurity / RAG practice (India-inspired, entirely synthetic).

Stores balances in INR *paise* (1 rupee = 100 paise). No logos, no live IFSC linkage.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# Bump when schema changes — stale DB rows are wiped (educational reset).
SCHEMA_VERSION = 8

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "database.db"


@contextmanager
def db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _table_columns(conn: sqlite3.Connection, name: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({name})").fetchall()
        return {str(r["name"]) for r in rows}
    except sqlite3.Error:
        return set()


def _needs_full_reset(conn: sqlite3.Connection) -> bool:
    current = conn.execute("PRAGMA user_version").fetchone()
    ver = int(current[0] if current else 0)
    cols = _table_columns(conn, "accounts")
    needed = {"ifsc_code", "branch_name", "balance_paise"}
    if cols and not needed.issubset(cols):
        return True
    return ver != SCHEMA_VERSION


def _maybe_reset_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    if not _needs_full_reset(conn):
        return

    cur.executescript(
        """
        PRAGMA foreign_keys = OFF;
        DROP TABLE IF EXISTS transactions;
        DROP TABLE IF EXISTS atm_cards;
        DROP TABLE IF EXISTS fixed_deposits;
        DROP TABLE IF EXISTS loans;
        DROP TABLE IF EXISTS business_profiles;
        DROP TABLE IF EXISTS accounts;
        DROP TABLE IF EXISTS customers;
        DROP TABLE IF EXISTS support_macros;
        DROP TABLE IF EXISTS admin_console_seed;
        DROP TABLE IF EXISTS credit_cards;
        PRAGMA foreign_keys = ON;
        """
    )


def init_db() -> None:
    """Rebuild schema when VERSION bumps; callers then run seed_if_empty."""
    with db_connection() as conn:
        _maybe_reset_schema(conn)
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                segment TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                pan_masked TEXT NOT NULL,
                nominee_name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL,                 -- 'user' | 'admin'
                password_hash TEXT NOT NULL,        -- pbkdf2_sha256$iter$salt$hash
                customer_id INTEGER,                -- NULL for admin accounts
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                account_number TEXT NOT NULL UNIQUE,
                nickname TEXT NOT NULL,
                account_type TEXT NOT NULL,
                ifsc_code TEXT NOT NULL,
                branch_name TEXT NOT NULL,
                balance_paise INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                posted_date TEXT NOT NULL,
                narration TEXT NOT NULL,
                amount_paise INTEGER NOT NULL,
                txn_type TEXT NOT NULL,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS fixed_deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                folio_number TEXT NOT NULL,
                tenure_months INTEGER NOT NULL,
                roi_percent REAL NOT NULL,
                principal_paise INTEGER NOT NULL,
                maturity_date TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                loan_account_number TEXT NOT NULL,
                product TEXT NOT NULL,
                sanction_paise INTEGER NOT NULL,
                roi_percent REAL NOT NULL,
                emi_paise INTEGER NOT NULL,
                tenor_months INTEGER NOT NULL,
                balance_outstanding_paise INTEGER NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS atm_cards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                card_last_four TEXT NOT NULL,
                variant TEXT NOT NULL,
                expiry_mm_yy TEXT NOT NULL,
                atm_enabled INTEGER NOT NULL,
                domestic_pos_enabled INTEGER NOT NULL,
                online_enabled INTEGER NOT NULL,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS business_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                gstin_masked TEXT NOT NULL,
                legal_name TEXT NOT NULL,
                current_account_number TEXT NOT NULL UNIQUE,
                od_limit_paise INTEGER NOT NULL DEFAULT 0,
                trade_finance_suite TEXT NOT NULL DEFAULT 'STANDARD_MSME',
                FOREIGN KEY (customer_id) REFERENCES customers(id)
            );

            CREATE TABLE IF NOT EXISTS support_macros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag TEXT NOT NULL,
                phrase TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_console_seed (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                note TEXT NOT NULL,
                staging_token_masked TEXT NOT NULL,
                training_corporate_host TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            """
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def seed_if_empty() -> None:
    with db_connection() as conn:
        n = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        if n:
            return

        cur = conn.cursor()

        BANK_IFSC = "DEMO0000452"

        CUSTOMERS = [
            (
                "Ananya Krishnan",
                "retail_sb",
                "ananya.krishnan.fake@mailbox.example",
                "+91 98763 55421",
                "ABCDE****Z",
                "Rohan Krishnan",
            ),
            (
                "Rohit Sharma",
                "retail_mixed",
                "rohit.sharma.fake@mailbox.example",
                "+91 98711 88904",
                "FGHIJ****K",
                "Priya Sharma",
            ),
            (
                "River Textiles Private Limited",
                "business",
                "finops.river.fake@mailbox.example",
                "+91 80 6611 9044",
                "LMNOP****Y",
                "Managing Director Desk",
            ),
            (
                "Suresh Venkatesan",
                "salary_ca",
                "suresh.v.fake@mailbox.example",
                "+91 98402 77311",
                "RSTUV****M",
                "Lakshmi Venkatesan",
            ),
            # From custemer.txt (practice cohort — DEMO IFSC in DB; see documents/custemer_practice_profiles.txt)
            (
                "Ravi Kumar",
                "retail_sb",
                "ravi.kumar@example.com",
                "+91 9876543210",
                "RVKU****A",
                "Practice nominee",
            ),
            (
                "Priya Sharma",
                "retail_current",
                "priya.sharma@example.com",
                "+91 9988776655",
                "PRSH****B",
                "Practice nominee",
            ),
            (
                "Arjun Patel",
                "retail_sb",
                "arjun.patel@example.com",
                "+91 9123456780",
                "ARPT****C",
                "Practice nominee",
            ),
            (
                "Sneha Reddy",
                "business",
                "sneha.reddy@example.com",
                "+91 9345678901",
                "SNRD****D",
                "Practice nominee",
            ),
            (
                "Karthik Raj",
                "retail_sb",
                "karthik.raj@example.com",
                "+91 9001122334",
                "KRRJ****E",
                "Practice nominee",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO customers (name, segment, email, phone, pan_masked, nominee_name)
            VALUES (?,?,?,?,?,?)
            """,
            CUSTOMERS,
        )

        # rupees × 100 = paise helpers below (all synthetic)
        def cid(offset: int) -> int:
            row = conn.execute(
                "SELECT id FROM customers ORDER BY id LIMIT 1 OFFSET ?",
                (offset,),
            ).fetchone()
            return int(row["id"])

        rid0 = cid(0)
        rid1 = cid(1)
        rid_biz = cid(2)
        rid2 = cid(3)
        rid_ravi = cid(4)
        rid_priya = cid(5)
        rid_arjun = cid(6)
        rid_sneha = cid(7)
        rid_karthik = cid(8)

        ACCOUNTS = [
            (
                rid0,
                "5010098145623791",
                "Samruddhi Savings",
                "SB",
                BANK_IFSC,
                "Chennai — Anna Nagar (Demo Branch)",
                38427543,
                "ACTIVE",
            ),
            (
                rid1,
                "5020134472891045",
                "Digi Savings Advantage",
                "SB",
                BANK_IFSC,
                "Chennai — Anna Nagar (Demo Branch)",
                12890650,
                "ACTIVE",
            ),
            (
                rid2,
                "6019984421038872",
                "Metro Salary Current",
                "CA",
                BANK_IFSC,
                "Chennai — Anna Nagar (Demo Branch)",
                217459900,
                "ACTIVE",
            ),
            (
                rid_biz,
                "3091148826673401",
                "River Textiles Ops Current",
                "CA_BUSINESS",
                BANK_IFSC,
                "Chennai — Mylapore SME Hub (Demo)",
                18439200000,
                "ACTIVE",
            ),
            (
                rid_ravi,
                "10000001",
                "Retail Savings — Custemer drill",
                "SB",
                "DEMO0001234",
                "Chennai Main Branch",
                5243000,
                "ACTIVE",
            ),
            (
                rid_priya,
                "10000002",
                "Classic Current — Custemer drill",
                "CA",
                "DEMO0004567",
                "Bangalore City Branch",
                12590000,
                "ACTIVE",
            ),
            (
                rid_arjun,
                "10000003",
                "Salary Savings — Custemer drill",
                "SB",
                "DEMO0007890",
                "Mumbai Central",
                8720000,
                "ACTIVE",
            ),
            (
                rid_sneha,
                "10000004",
                "Business Operating — Custemer drill",
                "CA_BUSINESS",
                "DEMO0001122",
                "Hyderabad Branch",
                24570000,
                "ACTIVE",
            ),
            (
                rid_karthik,
                "10000005",
                "Retail Savings — Custemer drill",
                "SB",
                "DEMO0003344",
                "Coimbatore Branch",
                7430000,
                "ACTIVE",
            ),
        ]

        cur.executemany(
            """
            INSERT INTO accounts (
                customer_id, account_number, nickname, account_type,
                ifsc_code, branch_name, balance_paise, status
            )
            VALUES (?,?,?,?,?,?,?,?)
            """,
            ACCOUNTS,
        )

        aids = {}
        for r in conn.execute("SELECT account_number, id FROM accounts"):
            aids[r["account_number"]] = r["id"]

        TXS = [
            (aids["5010098145623791"], "2026-05-03", "UPI-SETTLEMENT / SWIGGY", -84500, "DR"),
            (aids["5010098145623791"], "2026-05-06", "NEFT IN / ACME SOFT PVT LTD", 6523000, "CR"),
            (aids["5010098145623791"], "2026-05-07", "IMPS OUT / PARENT TRANSFER", -1500000, "DR"),
            (aids["5020134472891045"], "2026-05-07", "POS / BIG BASKET ONLINE", -320075, "DR"),
            (aids["5020134472891045"], "2026-05-08", "DIRECT CREDIT SALARY CREDIT MAY", 95000000, "CR"),
            (aids["6019984421038872"], "2026-05-02", "NEFT PAYABLE BATCH / LIC PREMIUM", -1845000, "DR"),
            (aids["3091148826673401"], "2026-05-03", "VENDOR ACH / WESTERN TEXTILES LLP", -432000500, "DR"),
            (aids["3091148826673401"], "2026-05-06", "INWARD LC PROCEEDS SETTLEMENT", 1800000300, "CR"),
            # custemer.txt style postings (amounts in paise)
            (aids["10000001"], "2026-05-04", "UPI PAYMENT / MERCHANT TXN001", -120000, "DR"),
            (aids["10000002"], "2026-05-05", "ATM WITHDRAWAL TXN002", -500000, "DR"),
            (aids["10000003"], "2026-05-06", "ONLINE SHOPPING TXN003", -345000, "DR"),
            (aids["10000004"], "2026-05-06", "BUSINESS TRANSFER TXN004 (PENDING FLAGS DEMO)", -12500000, "DR"),
            (aids["10000005"], "2026-05-07", "ELECTRICITY BILL TXN005", -230000, "DR"),
        ]
        cur.executemany(
            """
            INSERT INTO transactions (account_id, posted_date, narration, amount_paise, txn_type)
            VALUES (?,?,?,?,?)
            """,
            TXS,
        )

        FDS = [
            (
                rid0,
                "FD/2026/INV-98112",
                18,
                7.05,
                50000000,
                "2027-11-11",
                "ACTIVE",
            ),
            (
                rid1,
                "FD/2025/INV-76423",
                12,
                6.95,
                250000000,
                "2026-06-21",
                "ACTIVE",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO fixed_deposits (
                customer_id, folio_number, tenure_months, roi_percent,
                principal_paise, maturity_date, status
            )
            VALUES (?,?,?,?,?,?,?)
            """,
            FDS,
        )

        LOANS = [
            (
                rid0,
                "HLN-CHN-884021",
                "Floating Home Loan — Affordable Housing Drill (Synthetic)",
                8500000000,
                9.05,
                8620085,
                168,
                6930400200,
                "SANCTIONED_RUNNING",
            ),
            (
                rid1,
                "PL-CHN-332901",
                "Retail Personal Loan",
                6200000000,
                15.49,
                151500025,
                48,
                4850006000,
                "SANCTIONED_RUNNING",
            ),
            (
                rid_biz,
                "WC-CHN-BIZ-7742",
                "Working Capital — Cash Credit Hypothecation (Synthetic)",
                22500000000,
                11.85,
                245000050,
                120,
                18440090050,
                "SANCTIONED_RUNNING",
            ),
            (
                rid_ravi,
                "LN1001",
                "Home Loan (custemer.txt rehearsal)",
                2500000000,
                9.20,
                2450000,
                240,
                2187500000,
                "ACTIVE",
            ),
            (
                rid_priya,
                "LN1002",
                "Car Loan (custemer.txt rehearsal)",
                850000000,
                10.35,
                1320000,
                60,
                620000000,
                "APPROVED",
            ),
            (
                rid_sneha,
                "LN1003",
                "Business Loan (custemer.txt rehearsal)",
                4500000000,
                12.10,
                5800000,
                120,
                4410000000,
                "UNDER_REVIEW",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO loans (
                customer_id, loan_account_number, product, sanction_paise,
                roi_percent, emi_paise, tenor_months, balance_outstanding_paise, status
            )
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            LOANS,
        )

        CARDS = [
            (aids["5010098145623791"], "4421", "Classic RuPay Debit", "08/29", 1, 1, 1),
            (aids["5020134472891045"], "9087", "Platinum Mastercard Debit", "02/31", 1, 1, 0),
            (
                aids["6019984421038872"],
                "1134",
                "Contactless Visa Debit",
                "06/28",
                1,
                1,
                1,
            ),
            (
                aids["3091148826673401"],
                "6672",
                "Corporate Premium Debit",
                "11/30",
                1,
                1,
                1,
            ),
            (aids["10000001"], "9001", "RuPay Debit Practice", "03/30", 1, 1, 1),
            (aids["10000002"], "9002", "Visa Debit Practice", "07/29", 1, 1, 1),
            (aids["10000003"], "9003", "Mastercard Debit Practice", "01/31", 1, 1, 1),
            (aids["10000004"], "9004", "Business Debit Practice", "09/28", 1, 1, 1),
            (aids["10000005"], "9005", "RuPay Debit Practice", "05/30", 1, 1, 1),
        ]
        cur.executemany(
            """
            INSERT INTO atm_cards (
                account_id, card_last_four, variant, expiry_mm_yy,
                atm_enabled, domestic_pos_enabled, online_enabled
            )
            VALUES (?,?,?,?,?,?,?)
            """,
            CARDS,
        )

        BIZ_ROWS = [
            (
                rid_biz,
                "29AABCD1234E1ZC",
                "River Textiles Private Limited",
                "3091148826673401",
                5500000050,
                "CUSTOM_APOLLO_LC",
            ),
            (
                rid_sneha,
                "29AABCS7777E2ZD",
                "Sneha Reddy Enterprises (Practice)",
                "10000004",
                12000000000,
                "MSME_STANDARD_DRILL",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO business_profiles (
                customer_id, gstin_masked, legal_name, current_account_number,
                od_limit_paise, trade_finance_suite
            )
            VALUES (?,?,?,?,?,?)
            """,
            BIZ_ROWS,
        )

        cur.execute(
            """
            INSERT INTO admin_console_seed (note, staging_token_masked, training_corporate_host)
            VALUES (?,?,?)
            """,
            (
                "Synthetic admin scratchpad row for tabletop testing only.",
                "demo_staging_svc_****93af (FAKE)",
                "staging-corp-gateway.demo-region.local",
            ),
        )

        cur.executemany(
            "INSERT INTO support_macros (tag, phrase) VALUES (?,?)",
            [
                ("fraud_circle", "RBI phishing drill: Bharat Regional Bank NEVER asks for OTP/MPIN on phone."),
                ("netbank_lock", "If unsure, suspend netbanking instantly via IVR shortcut *99# DEMO path."),
            ],
        )

        # --- Demo login accounts (all synthetic) ---
        # Gmail-style plus aliases are supported because we store email as-is and validate loosely in API.
        # Passwords are for local practice only.
        cur.executemany(
            """
            INSERT INTO users (email, display_name, role, password_hash, customer_id, status)
            VALUES (?,?,?,?,?,?)
            """,
            [
                (
                    "admin+audit@gmail.test",
                    "Training Admin",
                    "admin",
                    hash_password("Admin@1234"),
                    None,
                    "ACTIVE",
                ),
                (
                    "ravi.kumar+demo@gmail.test",
                    "Ravi Kumar",
                    "user",
                    hash_password("Demo@1234"),
                    rid_ravi,
                    "ACTIVE",
                ),
                (
                    "priya.sharma+demo@gmail.test",
                    "Priya Sharma",
                    "user",
                    hash_password("Demo@1234"),
                    rid_priya,
                    "ACTIVE",
                ),
            ],
        )


def lookup_account(conn: sqlite3.Connection, account_number: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT a.*, c.name AS customer_name, c.segment AS customer_segment
        FROM accounts a
        JOIN customers c ON c.id = a.customer_id
        WHERE a.account_number = ?
        """,
        (account_number,),
    ).fetchone()


def hash_password(password: str, iterations: int = 210_000) -> str:
    """
    PBKDF2-SHA256 string format:
      pbkdf2_sha256$<iterations>$<hex_salt>$<hex_hash>
    """
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it_s, salt_hex, hash_hex = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(it_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def get_user_by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, email, display_name, role, password_hash, customer_id, status FROM users WHERE email = ?",
        (email,),
    ).fetchone()


def list_accounts_for_customer(conn: sqlite3.Connection, customer_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT account_number, nickname, account_type, branch_name, ifsc_code
        FROM accounts
        WHERE customer_id = ?
        ORDER BY id
        """,
        (customer_id,),
    ).fetchall()


__all__ = [
    "DB_PATH",
    "SCHEMA_VERSION",
    "db_connection",
    "init_db",
    "lookup_account",
    "seed_if_empty",
    "hash_password",
    "verify_password",
    "get_user_by_email",
    "list_accounts_for_customer",
]
