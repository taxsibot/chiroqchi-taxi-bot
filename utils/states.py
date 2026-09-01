from aiogram.fsm.state import StatesGroup, State

class Registration(StatesGroup):
    choosing_lang = State()
    choosing_role = State()
    entering_name = State()
    sending_phone = State()
    entering_secondary_phone = State()
    # Driver specific
    entering_car_name = State()
    entering_car_number = State()
    choosing_class = State()
    entering_car_photo = State()

class OrderProcess(StatesGroup):
    choosing_order_type = State() # Hozir / Bron
    waiting_for_date = State()
    waiting_for_time = State()
    entering_from = State()
    entering_to = State()
    entering_price = State()
    entering_passenger_count = State()
    waiting_for_parcel_type = State()
    waiting_for_parcel_receiver = State()
    waiting_for_parcel_photo = State()
    waiting_for_driver = State()
    updating_price = State()
    active_order = State()
    choosing_class = State()
    rating_driver = State()
    wait_for_location = State()

class ParcelProcess(StatesGroup):
    choosing_order_type = State()
    waiting_for_date = State()
    waiting_for_time = State()
    entering_from = State()
    entering_to = State()
    entering_price = State()
    waiting_for_parcel_type = State()
    waiting_for_parcel_receiver = State()
    waiting_for_parcel_photo = State()
    waiting_for_driver = State()
    updating_price = State()
    choosing_class = State()

class AdminStates(StatesGroup):
    # Advertising
    waiting_for_ad_content = State()
    waiting_for_ad_button_text = State()
    waiting_for_ad_button_url = State()
    waiting_for_admin_msg = State()
    waiting_for_media_ad = State()
    
    setting_config = State()
    
    # Channel Management
    adding_channel_id = State()
    adding_channel_link = State()
    
    # Promo Management
    adding_promo_code = State()
    adding_promo_amount = State()
    adding_promo_limit = State()
    adding_promo_material = State()
    
    # User/Driver/Order Management
    searching_user = State()
    searching_order = State()
    viewing_user_profile = State()
    entering_deposit_amount = State()
    entering_payment_amount = State()

    
    # Settings Management
    setting_min_price = State()
    setting_max_price = State()
    setting_commission = State()
    setting_order_limit = State()
    setting_balance = State()
    setting_is_paid_plan = State()
    # Settings
    waiting_for_setting_value = State()
    setting_tariff_daily_price = State()
    setting_tariff_monthly_price = State()
    setting_tariff_pax_price = State()
    setting_tariff_parcel_price = State()
    setting_tariff_pax_units = State()
    setting_tariff_parcel_units = State()
    setting_priority_price = State()
    setting_priority_delay = State()
    
    # Group Management
    adding_group_id = State()
    entering_group_link = State()
    
    # Content Editing
    waiting_for_content_text = State()
    
    # User Management
    # searching_user, entering_deposit_amount, waiting_for_admin_msg already defined above
    
    # Filters
    filtering_orders_date = State()
    filtering_logs_user = State()
    filtering_logs_date = State()
    
    # Promocode Management
    entering_promo_code = State()
    entering_promo_amount = State()
    entering_promo_limit = State()

    # Reports
    waiting_for_report_date = State()
    waiting_for_report_user_id = State()
    
    # Broadcast / Advertising
    # already defined above
    
    # Charity Management
    waiting_for_charity_card = State()
    waiting_for_charity_info = State()
    waiting_for_charity_total = State()
    waiting_for_charity_media = State()
    waiting_for_charity_title = State()
    waiting_for_charity_desc = State()
    waiting_for_charity_target = State()
    waiting_for_charity_expiry = State()
    
    # Auto Reply (FAQ)
    waiting_for_ar_keyword = State()
    waiting_for_ar_reply = State()
    
    # Manual Driver Addition
    adding_driver_id = State()
    adding_driver_car_name = State()
    adding_driver_car_number = State()

class SupportStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_reply = State()
    chatting_with_admin = State()

class DriverStates(StatesGroup):
    waiting_for_approval = State()
    setting_balance = State()
    entering_bid_amount = State()
    entering_car_name = State()
    editing_secondary_phone = State()
    # Driver specific
    editing_car_name = State()
    editing_car_number = State()
    editing_car_photo = State()

class PaymentStates(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_deposit_photo = State()
    waiting_for_receipt = State()
    waiting_for_withdraw_amount = State()
    waiting_for_withdraw_card = State()
    waiting_for_promo = State()
    waiting_for_charity_amount = State()
    waiting_for_charity_receipt = State()
    waiting_for_amount = State()  # Auto top-up amount input

class ProfileStates(StatesGroup):
    viewing = State()
    editing_name = State()
    editing_phone = State()
    editing_secondary_phone = State()
    # Driver specific
    editing_car_name = State()
    editing_car_number = State()
    editing_car_photo = State()

class ChatStates(StatesGroup):
    chatting = State()

class Emergency(StatesGroup):
    waiting_for_location = State()

class RideStates(StatesGroup):
    # Driver creating ride
    entering_from = State()
    entering_to = State()
    entering_time = State()
    entering_seats = State()
    entering_price = State()
    entering_notes = State()
    
    # Passenger booking ride
    choosing_seats = State()

class ReturnTripStates(StatesGroup):
    entering_from = State()
    entering_to = State()
    entering_time = State()
