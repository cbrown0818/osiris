import httpx


HOST_AGENT_URL = "http://host.docker.internal:5055"


async def get_host_health():
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{HOST_AGENT_URL}/health")
        response.raise_for_status()
        return response.json()


async def get_host_system_status():
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{HOST_AGENT_URL}/system/status")
        response.raise_for_status()
        return response.json()


async def get_host_gpu_status():
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(f"{HOST_AGENT_URL}/gpu/status")
        response.raise_for_status()
        return response.json()


async def get_host_docker_status():
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{HOST_AGENT_URL}/docker/status")
        response.raise_for_status()
        return response.json()


async def get_host_summary():
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{HOST_AGENT_URL}/summary")
        response.raise_for_status()
        return response.json()


async def get_host_security_status():
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{HOST_AGENT_URL}/security/status")
        response.raise_for_status()
        return response.json()
