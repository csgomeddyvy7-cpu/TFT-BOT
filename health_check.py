from aiohttp import web
import asyncio
import os

class HealthCheckServer:
    """Server health check cho Render.com"""
    
    def __init__(self, port=8080):
        self.port = int(os.getenv('PORT', port))
        self.app = web.Application()
        self.runner = None
        self.site = None
        
    def setup_routes(self):
        """Thiết lập routes"""
        self.app.router.add_get('/', self.handle_root)
        self.app.router.add_get('/health', self.handle_health)
        self.app.router.add_get('/ping', self.handle_ping)
    
    async def handle_root(self, request):
        """Trang chủ"""
        return web.Response(
            text='🚀 TFT Tracker Bot đang hoạt động!',
            content_type='text/plain'
        )
    
    async def handle_health(self, request):
        """Endpoint health check"""
        return web.json_response({
            'status': 'healthy',
            'service': 'tft-tracker-bot',
            'timestamp': asyncio.get_event_loop().time()
        })
    
    async def handle_ping(self, request):
        """Endpoint ping"""
        return web.Response(text='pong')
    
    async def start(self):
        """Khởi động server"""
        self.setup_routes()
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, '0.0.0.0', self.port)
        await self.site.start()
        print(f"✅ Health check server chạy trên port {self.port}")
    
    async def stop(self):
        """Dừng server"""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()