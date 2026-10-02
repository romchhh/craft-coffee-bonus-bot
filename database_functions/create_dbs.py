from database_functions.client_db import create_table 
from database_functions.links_db import create_table_links
from database_functions.admin_db import create_admins_table, init_superadmin
from database_functions.settings_db import create_settings_table
from database_functions.charge_db import migrate_loyalty_columns
from config import administrators


def create_dbs():
    create_table()
    create_settings_table()
    migrate_loyalty_columns()
    create_table_links()
    create_admins_table()
    
    if administrators:
        superadmin_id = administrators[0]
        init_superadmin(superadmin_id)

