from enum import Enum


class ContactAction(str, Enum):
    ADD = "ADD"
    REMOVE = "REMOVE"


class UserPayloadKey(str, Enum):
    CONTACT = "contact"
    CONTACTS = "contacts"
    SESSIONS = "sessions"
