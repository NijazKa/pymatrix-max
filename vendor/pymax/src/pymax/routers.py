from typing import TypeAlias

from pymax.client import Client
from pymax.client_web import WebClient
from pymax.dispatch.router import Router

ClientRouter: TypeAlias = Router[Client]
WebRouter: TypeAlias = Router[WebClient]
