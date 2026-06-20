from workers import WorkerEntrypoint

import asgi

from app.main import app as fastapi_app


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        fastapi_app.state.storycat_state = getattr(self.env, "STORYCAT_STATE", None)
        return await asgi.fetch(fastapi_app, request, self.env)
