from aiogram.fsm.state import State, StatesGroup

class UserSteps(StatesGroup):
    waiting_for_token = State()
    waiting_for_playlist = State()
    waiting_for_mp3 = State()
    uploading = State()
