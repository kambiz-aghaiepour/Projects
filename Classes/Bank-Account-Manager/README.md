# Bank Account Manager

**Category:** Classes · **Project:** `Classes/Bank-Account-Manager`

## Problem

Create a class called Account which will be an abstract class for three other
classes called CheckingAccount, SavingsAccount and BusinessAccount. Manage
credits and debits from these accounts through an ATM style program.

## Features

- Abstract `Account` with a shared transaction journal, deposit/withdraw
  template, fees and monthly close hook.
- **CheckingAccount**: overdraft up to a configurable limit with a flat fee
  when an overdraft begins.
- **SavingsAccount**: minimum balance, monthly interest at an annual rate, and
  six free withdrawals per month followed by a fee.
- **BusinessAccount**: credit line, monthly account fee and a per-debit
  transaction fee.
- `Bank` opens accounts with generated numbers (CHK-/SAV-/BUS-), transfers
  between accounts, runs month-end interest/fees and reports total deposits.
- Full statements with timestamps, signed amounts, running balance and notes.
- `BankError` / `ValueError` handling for insufficient funds, minimum balance
  breaches, exhausted credit, bad amounts and self-transfers.

## Requirements

Python 3.10+ (standard library only).

## Usage

```bash
python3 solution.py --demo
python3 solution.py
python3 solution.py --bank "My Credit Union"
```

- `--demo` runs a deterministic ATM session: opens three accounts, performs
  deposits, an overdraft, seven savings withdrawals, a business debit, a
  transfer, rejected operations, month-end processing and statements.
- `--bank NAME` names the bank in interactive mode.
- With no arguments the program presents an ATM-style menu: list accounts,
  open account, deposit, withdraw, transfer, statement, month-end, quit.

## Example Output

```
== Harbor Community Bank - ATM Demo ==

ACCOUNT    TYPE       OWNER                 BALANCE  RULES
------------------------------------------------------------------------------
CHK-1001   Checking   Alice Nguyen        $1,200.00  Overdraft up to $500.00; $35.00 fee when an overdraft begins.
SAV-2001   Savings    Alice Nguyen        $5,000.00  Min balance $100.00; 2.50% APY; 6 free withdrawals/month, then $10.00 each.
BUS-3001   Business   Acme Design LLC     $8,000.00  Credit line $5,000.00; $25.00/month; $0.75 per debit.

-- Checking activity --
  deposit $500        -> $1,700.00
  withdraw $200       -> $1,500.00
  withdraw $1,800     -> -$300.00 (overdraft fee $35.00 applied)
  deposit $400        -> $65.00

-- Savings activity (7 x $20, 6 free per month) --
  balance after 7 withdrawals: $4,850.00 (includes one $10.00 fee)

-- Month-end processing --
  INTEREST       +$10.10  monthly interest
  FEE            -$25.00  monthly account fee
  Total bank deposits: $11,913.50 -> $11,898.60

-- Statements --
Checking CHK-1001 - Alice Nguyen
Overdraft up to $500.00; $35.00 fee when an overdraft begins.
Balance: $565.00
WHEN              TYPE               AMOUNT       BALANCE  NOTE
------------------------------------------------------------------------------
2026-06-30 09:01  OPENING        +$1,200.00     $1,200.00  account opened
2026-06-30 09:04  DEPOSIT          +$500.00     $1,700.00
2026-06-30 09:06  WITHDRAWAL     -$1,800.00      -$300.00  rent
2026-06-30 09:07  FEE               -$35.00      -$335.00  overdraft fee
2026-06-30 09:28  DEPOSIT          +$500.00       $565.00  transfer from BUS-3001
```

## Implementation Notes

All money is `Decimal` quantised to cents; `Transaction` is an immutable
dataclass storing a signed amount and the balance after the entry. `Account`
implements the withdraw template: validate amount → `_authorize` (subclass
policy) → debit → record → `_settle_withdrawal` (subclass fee hook). Deposits
and interest go through equivalent record helpers so the journal always
balances.

`CheckingAccount` checks the projected balance including any overdraft fee
against its limit and charges the fee only when the balance crosses from
non-negative to negative. `SavingsAccount` rejects withdrawals that would
breach its minimum balance (including the extra-withdrawal fee when it applies),
counts withdrawals in the current calendar month for its free limit, and
accrues `balance × annual_rate / 12` at month end. `BusinessAccount` allows a
credit line including its per-debit fee on every withdrawal, and bills a
monthly fee.

`Bank` owns number generation, transfer atomicity (withdraw before deposit so a
failed withdrawal cannot credit the destination), and month-end iteration. The
demo injects a `FixedClock` so timestamps and output are reproducible. Statement
and summary rendering are O(transactions) and O(accounts) respectively.
