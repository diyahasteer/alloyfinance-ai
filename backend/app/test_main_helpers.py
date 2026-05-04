import os
import sys
import types
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql://example")
os.environ.setdefault("JWT_SECRET", "test-secret")

passlib_module = types.ModuleType("passlib")
passlib_context_module = types.ModuleType("passlib.context")


class _FakeCryptContext:
    def __init__(self, *args, **kwargs):
        pass

    def hash(self, password):
        return password

    def verify(self, plain_password, hashed_password):
        return plain_password == hashed_password


passlib_context_module.CryptContext = _FakeCryptContext
sys.modules.setdefault("passlib", passlib_module)
sys.modules.setdefault("passlib.context", passlib_context_module)

from app.main import (
    _add_finance_domain_context,
    _context_transaction_type,
    _extract_context_categories,
    _rewrite_common_category_aliases,
    _scope_transactions_sql,
)


class MainHelperTests(unittest.TestCase):
    def test_scope_transactions_sql_adds_user_scoped_cte(self):
        scoped = _scope_transactions_sql("SELECT * FROM transactions", "42")

        self.assertIn("WITH transactions AS (SELECT * FROM public.transactions WHERE user_id = 42)", scoped)
        self.assertTrue(scoped.endswith("SELECT * FROM transactions"))

    def test_scope_transactions_sql_merges_existing_with_clause(self):
        scoped = _scope_transactions_sql("WITH totals AS (SELECT 1) SELECT * FROM totals", "42")

        self.assertTrue(scoped.startswith("WITH transactions AS"))
        self.assertIn(", totals AS (SELECT 1)", scoped)

    def test_rewrite_common_category_aliases_maps_food_to_existing_categories(self):
        rewritten = _rewrite_common_category_aliases(
            "SELECT SUM(amount) FROM public.transactions WHERE spending_category = 'food'"
        )

        self.assertIn("spending_category IN ('groceries', 'dining')", rewritten)
        self.assertNotIn("= 'food'", rewritten)

    def test_finance_domain_context_mentions_valid_categories(self):
        context = _add_finance_domain_context("How much did I spend on food?")

        self.assertIn("groceries", context)
        self.assertIn("dining", context)
        self.assertIn("food as groceries and dining", context)

    def test_extract_context_categories_uses_question_and_sql(self):
        categories = _extract_context_categories(
            "How much did I spend on groceries?",
            "SELECT SUM(amount) FROM transactions",
        )

        self.assertEqual(categories, ["groceries"])

    def test_extract_context_categories_maps_food_to_groceries_and_dining(self):
        categories = _extract_context_categories(
            "How much did I spend on food?",
            "SELECT SUM(amount) FROM transactions WHERE spending_category IN ('groceries', 'dining')",
        )

        self.assertEqual(categories, ["groceries", "dining"])

    def test_context_transaction_type_uses_credit_for_income_questions(self):
        transaction_type = _context_transaction_type(
            "How much income did I receive?",
            "SELECT SUM(amount) FROM transactions WHERE spending_category = 'income'",
        )

        self.assertEqual(transaction_type, "credit")


if __name__ == "__main__":
    unittest.main()
