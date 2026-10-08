from database_functions.client_db import create_table
from database_functions.links_db import create_table_links
from database_functions.admin_db import create_admins_table, init_superadmin
from database_functions.settings_db import create_settings_table
from database_functions.charge_db import migrate_loyalty_columns
from database_functions.quests_db import create_quests_tables
from database_functions.referrals_db import create_referrals_table
from database_functions.promo_menu_db import create_promo_menu_table
from config import administrators


def create_dbs():
    create_table()
    create_settings_table()
    migrate_loyalty_columns()
    create_quests_tables()
    create_referrals_table()
    create_promo_menu_table()
    create_table_links()
    create_admins_table()

    if administrators:
        superadmin_id = administrators[0]
        init_superadmin(superadmin_id)

