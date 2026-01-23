from enum import Enum

from aiogram.filters.callback_data import CallbackData


class SimpleButtonName(str, Enum):
    MENU = "menu"
    NEW_MENU = "new_menu"
    NEW_ACCOUNT_ME = "new_account_me"
    DISPLAY_PLACEHOLDER = "display_placeholder"


class SimpleButtonCallbackData(CallbackData, prefix="simplebutton"):
    button_name: SimpleButtonName


class SimpleBoolCallbackData(CallbackData, prefix="simplebool"):
    result: bool


class AgentAgencyAction(str, Enum):
    OVERVIEW = "overview"
    TO_MEMBER_PANEL = "to_member_panel"
    TO_AGENT_PANEL = "to_agent_panel"
    NEW_PROFILE = "new_profile"


class AgentAgencyCallbackData(CallbackData, prefix="agent_agency"):
    pk: int
    action: AgentAgencyAction


class MemberAgencyAction(str, Enum):
    OVERVIEW = "overview"
    WALLET_CREDIT = "wallet_credit"
    LIST_AVAILABLE_PLANS = "list_available_plans"
    SEE_TOTURIAL_CONTENT = "see_toturial_content"


class MemberAgencyCallbackData(CallbackData, prefix="member_agency"):
    agency_id: int
    action: MemberAgencyAction


class MemberAgencyProfileAction(str, Enum):
    DETAIL = "detail"
    LIST_AVAILABLE_PLANS = "list_available_plans"
    PASS_CHANGE = "pass_change"
    TRANSFER_TO_ANOTHER = "transfer_to_another"
    SEE_PROXY_LIST = "see_proxy_list"


class MemberAgencyProfileCallbackData(CallbackData, prefix="profile"):
    profile_id: int
    action: MemberAgencyProfileAction


class MemberBillAction(str, Enum):
    OVERVIEW = "overview"
    CANCEL = "cancel"


class MemberBillCallbackData(CallbackData, prefix="member_init_paybill"):
    bill_id: int
    action: MemberBillAction
