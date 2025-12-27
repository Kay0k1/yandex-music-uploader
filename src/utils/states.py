from aiogram.fsm.state import State, StatesGroup

class UserSteps(StatesGroup):
    waiting_for_token = State()