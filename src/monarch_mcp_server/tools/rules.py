"""Transaction rules tools with GraphQL queries."""

import logging
from typing import Any, Dict, List, Optional

from gql import gql

from monarch_mcp_server.app import mcp
from monarch_mcp_server.client import get_monarch_client
from monarch_mcp_server.helpers import json_success, json_error

logger = logging.getLogger(__name__)


def _build_amount_criteria(
    operator: Optional[str],
    value: Optional[float],
    value_range: Optional[List[float]],
    is_expense: bool,
) -> Optional[Dict[str, Any]]:
    """Build an ``amountCriteria`` input, or None if underspecified.

    ``between`` requires a ``[lower, upper]`` range (mapped to ``valueRange``);
    every other operator (``eq``/``gt``/``lt``) uses a single ``value``.
    """
    if not operator:
        return None
    criteria: Dict[str, Any] = {
        "operator": operator,
        "isExpense": is_expense,
        "value": None,
        "valueRange": None,
    }
    if operator == "between":
        if not value_range or len(value_range) != 2:
            return None
        criteria["valueRange"] = {"lower": value_range[0], "upper": value_range[1]}
    else:
        if value is None:
            return None
        criteria["value"] = value
    return criteria


def _build_statement_criteria(
    operator: Optional[str],
    value: Optional[str],
    values: Optional[List[str]],
) -> Optional[List[Dict[str, Any]]]:
    """Build an ``originalStatementCriteria`` list (matches raw statement text).

    Accepts a single value or a list; all share one operator (default
    ``contains``). Returns None when no value is provided.
    """
    op = operator or "contains"
    vals = [v for v in (values or []) if v]
    if not vals and value:
        vals = [value]
    if not vals:
        return None
    return [{"operator": op, "value": v} for v in vals]


# ---------------------------------------------------------------------------
# GraphQL constants
# ---------------------------------------------------------------------------

GET_TRANSACTION_RULES_QUERY = gql("""
query GetTransactionRules {
  transactionRules {
    id
    order
    merchantCriteriaUseOriginalStatement
    merchantCriteria {
      operator
      value
      __typename
    }
    originalStatementCriteria {
      operator
      value
      __typename
    }
    merchantNameCriteria {
      operator
      value
      __typename
    }
    amountCriteria {
      operator
      isExpense
      value
      valueRange {
        lower
        upper
        __typename
      }
      __typename
    }
    categoryIds
    accountIds
    categories {
      id
      name
      icon
      __typename
    }
    accounts {
      id
      displayName
      __typename
    }
    setMerchantAction {
      id
      name
      __typename
    }
    setCategoryAction {
      id
      name
      icon
      __typename
    }
    addTagsAction {
      id
      name
      color
      __typename
    }
    linkGoalAction {
      id
      name
      __typename
    }
    setHideFromReportsAction
    reviewStatusAction
    recentApplicationCount
    lastAppliedAt
    __typename
  }
}
""")

CREATE_TRANSACTION_RULE_MUTATION = gql("""
mutation Common_CreateTransactionRuleMutationV2($input: CreateTransactionRuleInput!) {
  createTransactionRuleV2(input: $input) {
    errors {
      fieldErrors {
        field
        messages
        __typename
      }
      message
      code
      __typename
    }
    __typename
  }
}
""")

UPDATE_TRANSACTION_RULE_MUTATION = gql("""
mutation Common_UpdateTransactionRuleMutationV2($input: UpdateTransactionRuleInput!) {
  updateTransactionRuleV2(input: $input) {
    errors {
      fieldErrors {
        field
        messages
        __typename
      }
      message
      code
      __typename
    }
    __typename
  }
}
""")

DELETE_TRANSACTION_RULE_MUTATION = gql("""
mutation Common_DeleteTransactionRule($id: ID!) {
  deleteTransactionRule(id: $id) {
    deleted
    errors {
      fieldErrors {
        field
        messages
        __typename
      }
      message
      code
      __typename
    }
    __typename
  }
}
""")

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_transaction_rules() -> str:
    """
    Get all transaction auto-categorization rules from Monarch Money.

    Returns a list of rules with their conditions and actions.
    Rules automatically categorize transactions based on merchant, amount, etc.
    """
    try:
        client = await get_monarch_client()
        result = await client.gql_call(
            operation="GetTransactionRules",
            graphql_query=GET_TRANSACTION_RULES_QUERY,
            variables={},
        )

        rules_list = []
        for rule in result.get("transactionRules", []):
            rule_info = {
                "id": rule.get("id"),
                "order": rule.get("order"),
                "merchant_criteria": rule.get("merchantCriteria"),
                "merchant_name_criteria": rule.get("merchantNameCriteria"),
                "original_statement_criteria": rule.get("originalStatementCriteria"),
                "amount_criteria": rule.get("amountCriteria"),
                "category_ids": rule.get("categoryIds"),
                "account_ids": rule.get("accountIds"),
                "use_original_statement": rule.get("merchantCriteriaUseOriginalStatement"),
                "set_category_action": {
                    "id": rule.get("setCategoryAction", {}).get("id"),
                    "name": rule.get("setCategoryAction", {}).get("name"),
                } if rule.get("setCategoryAction") else None,
                "set_merchant_action": {
                    "id": rule.get("setMerchantAction", {}).get("id"),
                    "name": rule.get("setMerchantAction", {}).get("name"),
                } if rule.get("setMerchantAction") else None,
                "add_tags_action": [
                    {"id": tag.get("id"), "name": tag.get("name")}
                    for tag in rule.get("addTagsAction", [])
                ] if rule.get("addTagsAction") else None,
                "link_goal_action": rule.get("linkGoalAction"),
                "hide_from_reports_action": rule.get("setHideFromReportsAction"),
                "review_status_action": rule.get("reviewStatusAction"),
                "recent_application_count": rule.get("recentApplicationCount"),
                "last_applied_at": rule.get("lastAppliedAt"),
            }
            rules_list.append(rule_info)

        return json_success(rules_list)
    except Exception as e:
        return json_error("get_transaction_rules", e)


@mcp.tool()
async def create_transaction_rule(
    merchant_criteria_operator: Optional[str] = None,
    merchant_criteria_value: Optional[str] = None,
    merchant_criteria_values: Optional[List[str]] = None,
    original_statement_operator: Optional[str] = None,
    original_statement_value: Optional[str] = None,
    original_statement_values: Optional[List[str]] = None,
    amount_operator: Optional[str] = None,
    amount_value: Optional[float] = None,
    amount_value_range: Optional[List[float]] = None,
    amount_is_expense: bool = True,
    set_category_id: Optional[str] = None,
    set_merchant_name: Optional[str] = None,
    add_tag_ids: Optional[List[str]] = None,
    hide_from_reports: Optional[bool] = None,
    review_status: Optional[str] = None,
    account_ids: Optional[List[str]] = None,
    apply_to_existing: bool = False,
) -> str:
    """
    Create a new transaction auto-categorization rule.

    Rules automatically categorize future transactions based on conditions.

    Args:
        merchant_criteria_operator: How to match merchant ("eq", "contains")
        merchant_criteria_value: Merchant name/pattern to match
        merchant_criteria_values: Match any of several merchant patterns
        original_statement_operator: How to match the raw bank statement text
            ("eq", "contains")
        original_statement_value: Statement text to match. This is the best way
            to disambiguate a subscription from a merchant's other spending —
            e.g. match "UBER ONE" or "APPLE.COM/BILL" without touching regular
            Uber rides or Apple device purchases.
        original_statement_values: Match any of several statement patterns
        amount_operator: Amount comparison ("gt", "lt", "eq", "between")
        amount_value: Amount threshold for "gt"/"lt"/"eq"
        amount_value_range: [lower, upper] pair, required when operator is
            "between" (e.g. [9.0, 10.0] to match a ~$9.99 charge)
        amount_is_expense: Whether amount is expense (negative) or income
        set_category_id: Category ID to assign (use get_categories for IDs)
        set_merchant_name: Merchant name to set on matching transactions
        add_tag_ids: List of tag IDs to add (use get_tags for IDs)
        hide_from_reports: Whether to hide matching transactions from reports
        review_status: Review status to set ("needs_review" or null)
        account_ids: Limit rule to specific account IDs
        apply_to_existing: Whether to apply rule to existing transactions

    Returns:
        Result of rule creation.

    Example:
        Uber One subscription without touching rides:
        create_transaction_rule(
            original_statement_operator="contains",
            original_statement_value="UBER ONE",
            set_category_id="cat_123"
        )
    """
    try:
        client = await get_monarch_client()

        rule_input: Dict[str, Any] = {
            "applyToExistingTransactions": apply_to_existing,
        }

        # Accept either a single merchant value or a list of values. When a
        # list is given, build one criterion per value sharing the operator
        # (defaults to "contains"). This lets one rule match many merchants.
        _merchant_op = merchant_criteria_operator or "contains"
        _merchant_values = [v for v in (merchant_criteria_values or []) if v]
        if not _merchant_values and merchant_criteria_value:
            _merchant_values = [merchant_criteria_value]
        if _merchant_values:
            rule_input["merchantNameCriteria"] = [
                {"operator": _merchant_op, "value": v} for v in _merchant_values
            ]

        statement_criteria = _build_statement_criteria(
            original_statement_operator,
            original_statement_value,
            original_statement_values,
        )
        if statement_criteria:
            rule_input["originalStatementCriteria"] = statement_criteria

        amount_criteria = _build_amount_criteria(
            amount_operator, amount_value, amount_value_range, amount_is_expense
        )
        if amount_criteria:
            rule_input["amountCriteria"] = amount_criteria

        if account_ids:
            rule_input["accountIds"] = account_ids

        if set_category_id:
            rule_input["setCategoryAction"] = set_category_id
        if set_merchant_name:
            rule_input["setMerchantAction"] = set_merchant_name
        if add_tag_ids:
            rule_input["addTagsAction"] = add_tag_ids
        if hide_from_reports is not None:
            rule_input["setHideFromReportsAction"] = hide_from_reports
        if review_status:
            rule_input["reviewStatusAction"] = review_status

        result = await client.gql_call(
            operation="Common_CreateTransactionRuleMutationV2",
            graphql_query=CREATE_TRANSACTION_RULE_MUTATION,
            variables={"input": rule_input},
        )

        errors = result.get("createTransactionRuleV2", {}).get("errors")
        if errors:
            return json_success({"success": False, "errors": errors})

        return json_success({"success": True, "message": "Rule created successfully"})
    except Exception as e:
        return json_error("create_transaction_rule", e)


@mcp.tool()
async def update_transaction_rule(
    rule_id: str,
    merchant_criteria_operator: Optional[str] = None,
    merchant_criteria_value: Optional[str] = None,
    merchant_criteria_values: Optional[List[str]] = None,
    original_statement_operator: Optional[str] = None,
    original_statement_value: Optional[str] = None,
    original_statement_values: Optional[List[str]] = None,
    amount_operator: Optional[str] = None,
    amount_value: Optional[float] = None,
    amount_value_range: Optional[List[float]] = None,
    amount_is_expense: bool = True,
    set_category_id: Optional[str] = None,
    set_merchant_name: Optional[str] = None,
    add_tag_ids: Optional[List[str]] = None,
    hide_from_reports: Optional[bool] = None,
    review_status: Optional[str] = None,
    account_ids: Optional[List[str]] = None,
    apply_to_existing: bool = False,
) -> str:
    """
    Update an existing transaction rule.

    Args:
        rule_id: The ID of the rule to update (use get_transaction_rules to find IDs)
        merchant_criteria_operator: How to match merchant ("eq", "contains")
        merchant_criteria_value: Merchant name/pattern to match
        merchant_criteria_values: Match any of several merchant patterns
        original_statement_operator: How to match raw statement text ("eq", "contains")
        original_statement_value: Statement text to match (e.g. "UBER ONE")
        original_statement_values: Match any of several statement patterns
        amount_operator: Amount comparison ("gt", "lt", "eq", "between")
        amount_value: Amount threshold for "gt"/"lt"/"eq"
        amount_value_range: [lower, upper] pair, required when operator is "between"
        amount_is_expense: Whether amount is expense (negative) or income
        set_category_id: Category ID to assign
        set_merchant_name: Merchant name to set
        add_tag_ids: List of tag IDs to add
        hide_from_reports: Whether to hide from reports
        review_status: Review status to set
        account_ids: Limit rule to specific accounts
        apply_to_existing: Apply changes to existing transactions

    Returns:
        Result of rule update.
    """
    try:
        client = await get_monarch_client()

        rule_input: Dict[str, Any] = {
            "id": rule_id,
            "applyToExistingTransactions": apply_to_existing,
        }

        # Accept either a single merchant value or a list of values. When a
        # list is given, build one criterion per value sharing the operator
        # (defaults to "contains"). This lets one rule match many merchants.
        _merchant_op = merchant_criteria_operator or "contains"
        _merchant_values = [v for v in (merchant_criteria_values or []) if v]
        if not _merchant_values and merchant_criteria_value:
            _merchant_values = [merchant_criteria_value]
        if _merchant_values:
            rule_input["merchantNameCriteria"] = [
                {"operator": _merchant_op, "value": v} for v in _merchant_values
            ]

        statement_criteria = _build_statement_criteria(
            original_statement_operator,
            original_statement_value,
            original_statement_values,
        )
        if statement_criteria:
            rule_input["originalStatementCriteria"] = statement_criteria

        amount_criteria = _build_amount_criteria(
            amount_operator, amount_value, amount_value_range, amount_is_expense
        )
        if amount_criteria:
            rule_input["amountCriteria"] = amount_criteria

        if account_ids:
            rule_input["accountIds"] = account_ids

        if set_category_id:
            rule_input["setCategoryAction"] = set_category_id
        if set_merchant_name:
            rule_input["setMerchantAction"] = set_merchant_name
        if add_tag_ids:
            rule_input["addTagsAction"] = add_tag_ids
        if hide_from_reports is not None:
            rule_input["setHideFromReportsAction"] = hide_from_reports
        if review_status:
            rule_input["reviewStatusAction"] = review_status

        result = await client.gql_call(
            operation="Common_UpdateTransactionRuleMutationV2",
            graphql_query=UPDATE_TRANSACTION_RULE_MUTATION,
            variables={"input": rule_input},
        )

        errors = result.get("updateTransactionRuleV2", {}).get("errors")
        if errors:
            return json_success({"success": False, "errors": errors})

        return json_success({"success": True, "message": "Rule updated successfully"})
    except Exception as e:
        return json_error("update_transaction_rule", e)


@mcp.tool()
async def delete_transaction_rule(rule_id: str) -> str:
    """
    Delete a transaction rule.

    Args:
        rule_id: The ID of the rule to delete (use get_transaction_rules to find IDs)

    Returns:
        Confirmation of deletion.
    """
    try:
        client = await get_monarch_client()

        result = await client.gql_call(
            operation="Common_DeleteTransactionRule",
            graphql_query=DELETE_TRANSACTION_RULE_MUTATION,
            variables={"id": rule_id},
        )

        # Monarch's deleteTransactionRule can return a payload where the
        # `deleted` flag is absent/null even when the deletion succeeded, which
        # previously produced a false "Unknown error". Treat an explicit errors
        # payload (or deleted == False) as failure; otherwise the mutation was
        # accepted and the rule is gone.
        delete_result = result.get("deleteTransactionRule") or {}

        errors = delete_result.get("errors")
        if errors:
            return json_success({"success": False, "errors": errors})

        if delete_result.get("deleted") is False:
            return json_success({"success": False, "message": "Rule was not deleted"})

        return json_success({"success": True, "message": "Rule deleted successfully"})
    except Exception as e:
        return json_error("delete_transaction_rule", e)
