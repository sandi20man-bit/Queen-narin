#!/usr/bin/env python3
"""
Keep-Alive System for Telegram Bot
==================================

File ini membantu menjaga bot tetap aktif di development environment
dengan sistem ping internal dan monitoring.
"""

import asyncio
import aiohttp
import time
import os
from datetime import datetime

class KeepAlive:
    def __init__(self, ping_interval=300):  # 5 menit
        """
        Initialize keep-alive system
        
        Args:
            ping_interval (int): Interval ping dalam detik (default: 5 menit)
        """
        self.ping_interval = ping_interval
        self.start_time = time.time()
        self.ping_count = 0
        self.is_running = False
        
    async def ping_self(self):
        """Internal ping untuk menjaga aktivitas"""
        try:
            # Ping ke localhost untuk menjaga aktivitas
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost:8080', timeout=5) as response:
                    pass
        except:
            # Jika gagal ping localhost, buat activity lain
            pass
            
        self.ping_count += 1
        uptime = time.time() - self.start_time
        current_time = datetime.now().strftime("%H:%M:%S")
        
        print(f"⏰ [{current_time}] Keep-alive ping #{self.ping_count} | Uptime: {uptime/60:.1f} menit")
    
    async def start_keep_alive(self):
        """Mulai sistem keep-alive"""
        self.is_running = True
        self.start_time = time.time()
        
        print(f"🟢 Keep-alive system started (ping setiap {self.ping_interval/60:.1f} menit)")
        
        while self.is_running:
            await asyncio.sleep(self.ping_interval)
            await self.ping_self()
    
    def stop_keep_alive(self):
        """Hentikan sistem keep-alive"""
        self.is_running = False
        uptime = time.time() - self.start_time
        print(f"🔴 Keep-alive system stopped | Total uptime: {uptime/60:.1f} menit | Total pings: {self.ping_count}")

# Instance global untuk digunakan di main.py
keep_alive_system = KeepAlive(ping_interval=300)  # Ping setiap 5 menit

async def start_keep_alive():
    """Helper function untuk memulai keep-alive"""
    await keep_alive_system.start_keep_alive()

def stop_keep_alive():
    """Helper function untuk menghentikan keep-alive"""
    keep_alive_system.stop_keep_alive()

if __name__ == "__main__":
    # Test keep-alive system
    async def test():
        await start_keep_alive()
    
    try:
        asyncio.run(test())
    except KeyboardInterrupt:
        stop_keep_alive()
        print("Keep-alive test selesai")