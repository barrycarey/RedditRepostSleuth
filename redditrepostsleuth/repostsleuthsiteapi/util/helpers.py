from typing import Dict

from redditrepostsleuth.core.db.uow.unitofworkmanager import UnitOfWorkManager


def is_site_admin(user_data: Dict, uowm: UnitOfWorkManager) -> bool:
    if 'name' not in user_data:
        return False
    if user_data['name'].lower() in ['barrycarey', 'repostsleuthbot']:
        return True
    return False