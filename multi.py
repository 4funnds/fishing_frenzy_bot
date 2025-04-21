<<<<<<< HEAD
import asyncio
import aiohttp
import json
import os
import random
import time
from datetime import datetime, timedelta
import logging
from colorama import Fore, Style, init
import sys

if sys.platform == 'win32':
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize colorama for cross-platform colored terminal output
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
)
logger = logging.getLogger(__name__)

# Configuration
config = {
    "api_base_url": "https://api.fishingfrenzy.co",
    "ws_url": "wss://api.fishingfrenzy.co",
    "fishing_range": "long_range",
    "is_5x": False,
    "delay_between_fishing": 5,  # seconds
    "retry_delay": 30,  # seconds
    "max_retries": 1,
    "energy_refresh_hours": 0.1,
    "range_costs": {
        "short_range": 1,
        "mid_range": 2,
        "long_range": 3
    },
    "account_switch_delay": 10,  # seconds
    "concurrent_fishing_limit": 10  # Maximum concurrent fishing activities
}

# Account-specific data
account_states = []

# Load tokens from file
def load_tokens():
    try:
        with open('tokens.txt', 'r', encoding='utf-8') as file:
            tokens = [token.strip() for token in file.readlines() if token.strip()]
        
        if not tokens:
            logger.error(f"{Fore.RED}No valid tokens found in tokens.txt")
            exit(1)
        
        return tokens
    except Exception as e:
        logger.error(f"{Fore.RED}Failed to read tokens.txt: {str(e)}")
        exit(1)

# Initialize account states from tokens
def initialize_account_states(tokens):
    for token in tokens:
        account_states.append({
            "auth_token": token,
            "current_energy": 0,
            "retry_count": 0,
            "energy_refresh_time": None,
            "headers": {
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.6',
                'authorization': f'Bearer {token}',
                'content-type': 'application/json',
                'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Brave";v="134"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'sec-gpc': '1',
                'Referer': 'https://fishingfrenzy.co/',
                'Referrer-Policy': 'strict-origin-when-cross-origin',
                'cache-control': 'no-cache',
                'pragma': 'no-cache'
            }
        })

# Utility functions for colored output
def log_success(msg):
    logger.info(f"{Fore.GREEN}{msg}")

def log_info(msg):
    logger.info(f"{msg}")

def log_warn(msg):
    logger.info(f"{Fore.YELLOW}{msg}")

def log_error(msg):
    logger.info(f"{Fore.RED}{msg}")

def log_highlight(label, value):
    logger.info(f"{label}: {Fore.CYAN}{value}")

def display_banner():
    banner = [
        f"{Fore.CYAN}==================================================",
        f"{Fore.CYAN}    Fishing Frenzy Auto Bot - Airdrop Insiders    ",
        f"{Fore.CYAN}=================================================="
    ]
    for line in banner:
        logger.info(line)

def display_profile_info(data, account_index):
    log_success(f"[Account {account_index + 1}] Profile Loaded Successfully!")
    log_info(f"[Account {account_index + 1}] User ID: {data.get('userId', 'N/A')}")
    logger.info(f"[Account {account_index + 1}] Gold: {data.get('gold', 0)}")
    log_highlight(f"[Account {account_index + 1}] Energy", f"{data.get('energy', 0)}")
    logger.info(f"[Account {account_index + 1}] Fish Points: {data.get('fishPoint', 0)}")
    logger.info(f"[Account {account_index + 1}] EXP: {data.get('exp', 0)}")

def format_time_remaining(milliseconds):
    seconds = int((milliseconds / 1000) % 60)
    minutes = int((milliseconds / (1000 * 60)) % 60)
    hours = int(milliseconds / (1000 * 60 * 60))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

async def check_inventory(session, account):
    account_index = account_states.index(account)
    try:
        async with session.get(f"{config['api_base_url']}/v1/inventory", headers=account["headers"]) as response:
            if response.status == 200:
                data = await response.json()
                account["current_energy"] = data.get("energy", 0)
                return data
            else:
                log_error(f"[Account {account_index + 1}] Failed to check inventory: {response.status}")
                if response.status == 503:
                    log_warn(f"[Account {account_index + 1}] Server temporarily unavailable")
                return None
    except Exception as e:
        log_error(f"[Account {account_index + 1}] Error checking inventory: {str(e)}")
        return None

def select_fishing_range(account):
    account_index = account_states.index(account)
    available_ranges = []
    
    if account["current_energy"] >= config["range_costs"]["long_range"]:
        available_ranges.append("long_range")
    elif account["current_energy"] >= config["range_costs"]["mid_range"]:
        available_ranges.append("mid_range")
    elif account["current_energy"] >= config["range_costs"]["short_range"]:
        available_ranges.append("short_range")
    
    if not available_ranges:
        log_warn(f"[Account {account_index + 1}] No fishing ranges available with current energy!")
        return "short_range"
    
    selected_range = random.choice(available_ranges)
    if config["fishing_range"] != selected_range:
        config["fishing_range"] = selected_range
        log_info(f"[Account {account_index + 1}] Selected fishing range: {Fore.CYAN}{selected_range} (Cost: {config['range_costs'][selected_range]} energy)")
    
    return selected_range

def interpolate_points(p0, p1, steps):
    pts = []
    for i in range(1, steps):
        t = i / steps
        x = round(p0[0] + (p1[0] - p0[0]) * t)
        y = round(p0[1] + (p1[1] - p0[1]) * t)
        pts.append([x, y])
    return pts

def calculate_position_x(frame, direction):
    return 450 + frame * 2 + direction * 5

def calculate_position_y(frame, direction):
    return 426 + frame * 2 - direction * 3

async def fish(account):
    account_index = account_states.index(account)
    
    async def ws_fishing():
        key_frames = []
        required_frames = 10
        interpolation_steps = 30
        end_sent = False
        game_started = False
        game_success = False
        
        try:
            # Create a separate session for WebSocket connection
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"{config['ws_url']}/?token={account['auth_token']}") as ws:
                    # Send prepare command
                    await ws.send_str(json.dumps({
                        "cmd": "prepare",
                        "range": config["fishing_range"],
                        "is5x": config["is_5x"]
                    }))
                    
                    # Set a timeout for the entire fishing operation
                    start_time = time.time()
                    max_time = 60  # 60 seconds timeout
                    
                    while time.time() - start_time < max_time:
                        try:
                            # Receive message with timeout
                            msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                            
                            # Handle different message types
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                message = json.loads(msg.data)
                                
                                if message.get("type") == "initGame":
                                    game_started = True
                                    await ws.send_str(json.dumps({"cmd": "start"}))
                                
                                elif message.get("type") == "gameState":
                                    frame = message.get("frame", 0)
                                    direction = message.get("dir", 0)
                                    x = calculate_position_x(frame, direction)
                                    y = calculate_position_y(frame, direction)
                                    entry = [x, y, frame, direction] if direction != 0 else [x, y]
                                    key_frames.append(entry)
                                    
                                    if len(key_frames) == required_frames and not end_sent:
                                        final_frames = []
                                        if len(key_frames) < 2:
                                            final_frames = key_frames.copy()
                                        else:
                                            final_frames.append(key_frames[0])
                                            for i in range(1, len(key_frames)):
                                                prev = key_frames[i-1][:2]
                                                curr = key_frames[i][:2]
                                                interpolated = interpolate_points(prev, curr, interpolation_steps)
                                                final_frames.extend(interpolated)
                                                final_frames.append(key_frames[i])
                                        
                                        end_command = {
                                            "cmd": "end",
                                            "rep": {
                                                "fs": 100,
                                                "ns": 200,
                                                "fps": 20,
                                                "frs": final_frames
                                            },
                                            "en": 1
                                        }
                                        await ws.send_str(json.dumps(end_command))
                                        end_sent = True
                                
                                elif message.get("type") == "gameOver":
                                    game_success = message.get("success", False)
                                    if game_success:
                                        fish_info = message["catchedFish"]["fishInfo"]
                                        log_success(f"[Account {account_index + 1}] Successfully caught a {Fore.CYAN}{fish_info['fishName']} (quality: {fish_info['quality']}) worth {fish_info['sellPrice']} coins and {fish_info['expGain']} XP!")
                                        log_info(f"[Account {account_index + 1}] ⭐ Current XP: {message['catchedFish']['currentExp']}/{message['catchedFish']['expToNextLevel']}")
                                        log_highlight(f"[Account {account_index + 1}] ⚡ Remaining Energy", f"{message['catchedFish']['energy']}")
                                        logger.info(f"[Account {account_index + 1}] 💰 Gold: {message['catchedFish']['gold']}")
                                        logger.info(f"[Account {account_index + 1}] 🐟 Fish Points: {message['catchedFish']['fishPoint']}")
                                    else:
                                        log_error(f"[Account {account_index + 1}] Failed to catch fish")
                                        log_highlight(f"[Account {account_index + 1}] ⚡ Remaining Energy", f"{message['catchedFish']['energy']}")
                                        logger.info(f"[Account {account_index + 1}] 💰 Gold: {message['catchedFish']['gold']}")
                                        logger.info(f"[Account {account_index + 1}] 🐟 Fish Points: {message['catchedFish']['fishPoint']}")
                                    
                                    account["current_energy"] = message["catchedFish"]["energy"]
                                    return game_success
                            
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                # Handle binary message - convert to text if possible
                                try:
                                    message = json.loads(msg.data.decode('utf-8'))
                                    # Process the same way as text messages
                                    if message.get("type") == "initGame":
                                        game_started = True
                                        await ws.send_str(json.dumps({"cmd": "start"}))
                                    
                                    # ... other message handling same as above
                                except Exception as e:
                                    log_warn(f"[Account {account_index + 1}] Received binary data but couldn't parse: {str(e)}")
                            
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                log_warn(f"[Account {account_index + 1}] WebSocket connection closed")
                                break
                                
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                log_error(f"[Account {account_index + 1}] WebSocket connection error")
                                break
                                
                        except asyncio.TimeoutError:
                            # This is just a timeout on receive, not the entire operation
                            log_warn(f"[Account {account_index + 1}] Timeout waiting for WebSocket message")
                            continue
                        except Exception as e:
                            log_error(f"[Account {account_index + 1}] Error processing WebSocket message: {str(e)}")
                            continue
                    
                    # If we reach here without returning, it's a timeout
                    if not game_success:
                        log_error(f"[Account {account_index + 1}] Fishing operation timed out after {max_time} seconds")
                        return False
        
        except Exception as e:
            log_error(f"[Account {account_index + 1}] WebSocket connection error: {str(e)}")
            return False
    
    return await ws_fishing()

async def show_energy_countdown(account):
    account_index = account_states.index(account)
    if not account["energy_refresh_time"]:
        return
    
    log_warn(f"[Account {account_index + 1}] Out of energy. Waiting for energy to refresh...")
    
    while datetime.now() < account["energy_refresh_time"]:
        time_remaining = (account["energy_refresh_time"] - datetime.now()).total_seconds() * 1000
        print(f"\r[Account {account_index + 1}] Energy will refresh in: {Fore.CYAN}{format_time_remaining(time_remaining)}", end="")
        await asyncio.sleep(1)
    
    print("\n")
    log_success(f"[Account {account_index + 1}] Energy should be refreshed now!")
    account["energy_refresh_time"] = None
    await asyncio.sleep(5)

async def process_account(session, account):
    account_index = account_states.index(account)
    log_info(f"[Account {account_index + 1}] Starting Fishing Frenzy bot...")
    
    try:
        profile_data = await check_inventory(session, account)
        if not profile_data:
            log_warn(f"[Account {account_index + 1}] Failed to load profile, skipping...")
            return False
        
        display_profile_info(profile_data, account_index)
        
        if account["current_energy"] <= 0:
            if not account["energy_refresh_time"]:
                account["energy_refresh_time"] = datetime.now() + timedelta(hours=config["energy_refresh_hours"])
            await show_energy_countdown(account)
            return False
        
        select_fishing_range(account)
        
        log_info(f"[Account {account_index + 1}] 🎣 Starting fishing attempt with {Fore.CYAN}{config['fishing_range']}... (Energy cost: {config['range_costs'][config['fishing_range']]})")
        success = await fish(account)
        
        if success:
            log_success(f"[Account {account_index + 1}] Fishing attempt completed successfully. Waiting {config['delay_between_fishing']} seconds...")
            await asyncio.sleep(config["delay_between_fishing"])
            account["retry_count"] = 0
            return True
        else:
            account["retry_count"] += 1
            wait_time = config["retry_delay"] * 3 if account["retry_count"] > config["max_retries"] else config["retry_delay"]
            log_warn(f"[Account {account_index + 1}] Fishing attempt failed. Retry {account['retry_count']}/{config['max_retries']}. Waiting {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            return False
    
    except Exception as e:
        log_error(f"[Account {account_index + 1}] Error during fishing attempt: {str(e)}")
        account["retry_count"] += 1
        wait_time = 60 if account["retry_count"] > config["max_retries"] else 10
        log_warn(f"[Account {account_index + 1}] Error occurred. Retry {account['retry_count']}/{config['max_retries']}. Waiting {wait_time} seconds...")
        await asyncio.sleep(wait_time)
        return False

async def batch_fishing(accounts):
    log_info(f"Starting batch fishing with {len(accounts)} accounts...")
    
    async with aiohttp.ClientSession() as session:
        fishing_tasks = []
        
        for account in accounts:
            fishing_tasks.append(process_account(session, account))
        
        results = await asyncio.gather(*fishing_tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False)
        errors = sum(1 for r in results if isinstance(r, Exception))
        
        log_info(f"Batch fishing completed: {successful} successful, {failed} failed, {errors} errors")

async def run_bot():
    display_banner()
    
    # Load tokens and initialize account states
    tokens = load_tokens()
    initialize_account_states(tokens)
    
    log_info('------------------------------------------------------')
    log_info(f"Found {len(account_states)} accounts to process")
    logger.info("Fishing ranges available:")
    logger.info(f"- short_range: {config['range_costs']['short_range']} energy")
    logger.info(f"- mid_range: {config['range_costs']['mid_range']} energy")
    logger.info(f"- long_range: {config['range_costs']['long_range']} energy")
    logger.info(f"Retries: {config['max_retries']}, Delay between fishing: {config['delay_between_fishing']}s")
    logger.info(f"Energy refresh period: {config['energy_refresh_hours']} hours")
    logger.info(f"Account switch delay: {config['account_switch_delay']}s")
    logger.info(f"Concurrent fishing limit: {config['concurrent_fishing_limit']}")
    log_info('------------------------------------------------------')
    
    while True:
        # Group accounts into batches of concurrent_fishing_limit
        batch_size = config["concurrent_fishing_limit"]
        account_batches = [account_states[i:i+batch_size] for i in range(0, len(account_states), batch_size)]
        
        for batch in account_batches:
            await batch_fishing(batch)
            log_info(f"Batch completed. Waiting {config['account_switch_delay']} seconds before next batch...")
            await asyncio.sleep(config["account_switch_delay"])
        
        # Add a small delay before restarting the cycle
        await asyncio.sleep(5)

# Main entry point
if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("\nBot stopped by user")
    except Exception as e:
        log_error(f"Fatal error in bot: {str(e)}")
        log_warn("Bot will restart in 1 minute...")
        time.sleep(60)
        try:
            asyncio.run(run_bot())
        except Exception as e:
=======
import asyncio
import aiohttp
import json
import os
import random
import time
from datetime import datetime, timedelta
import logging
from colorama import Fore, Style, init
import sys

if sys.platform == 'win32':
	asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Initialize colorama for cross-platform colored terminal output
init(autoreset=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
)
logger = logging.getLogger(__name__)

# Configuration
config = {
    "api_base_url": "https://api.fishingfrenzy.co",
    "ws_url": "wss://api.fishingfrenzy.co",
    "fishing_range": "mid_range",
    "is_5x": False,
    "delay_between_fishing": 7,  # seconds
    "retry_delay": 30,  # seconds
    "max_retries": 2,
    "energy_refresh_hours": 0.1,
    "range_costs": {
        "short_range": 1,
        "mid_range": 2,
        "long_range": 3
    },
    "account_switch_delay": 10,  # seconds
    "concurrent_fishing_limit": 10  # Maximum concurrent fishing activities
}

# Account-specific data
account_states = []

# Load tokens from file
def load_tokens():
    try:
        with open('tokens.txt', 'r', encoding='utf-8') as file:
            tokens = [token.strip() for token in file.readlines() if token.strip()]
        
        if not tokens:
            logger.error(f"{Fore.RED}No valid tokens found in tokens.txt")
            exit(1)
        
        return tokens
    except Exception as e:
        logger.error(f"{Fore.RED}Failed to read tokens.txt: {str(e)}")
        exit(1)

# Initialize account states from tokens
def initialize_account_states(tokens):
    for token in tokens:
        account_states.append({
            "auth_token": token,
            "current_energy": 0,
            "retry_count": 0,
            "energy_refresh_time": None,
            "headers": {
                'accept': 'application/json',
                'accept-language': 'en-US,en;q=0.6',
                'authorization': f'Bearer {token}',
                'content-type': 'application/json',
                'sec-ch-ua': '"Chromium";v="134", "Not:A-Brand";v="24", "Brave";v="134"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'sec-gpc': '1',
                'Referer': 'https://fishingfrenzy.co/',
                'Referrer-Policy': 'strict-origin-when-cross-origin',
                'cache-control': 'no-cache',
                'pragma': 'no-cache'
            }
        })

# Utility functions for colored output
def log_success(msg):
    logger.info(f"{Fore.GREEN}{msg}")

def log_info(msg):
    logger.info(f"{msg}")

def log_warn(msg):
    logger.info(f"{Fore.YELLOW}{msg}")

def log_error(msg):
    logger.info(f"{Fore.RED}{msg}")

def log_highlight(label, value):
    logger.info(f"{label}: {Fore.CYAN}{value}")

def display_banner():
    banner = [
        f"{Fore.CYAN}==================================================",
        f"{Fore.CYAN}    Fishing Frenzy Auto Bot - Airdrop Insiders    ",
        f"{Fore.CYAN}=================================================="
    ]
    for line in banner:
        logger.info(line)

def display_profile_info(data, account_index):
    log_success(f"[Account {account_index + 1}] Profile Loaded Successfully!")
    log_info(f"[Account {account_index + 1}] User ID: {data.get('userId', 'N/A')}")
    logger.info(f"[Account {account_index + 1}] Gold: {data.get('gold', 0)}")
    log_highlight(f"[Account {account_index + 1}] Energy", f"{data.get('energy', 0)}")
    logger.info(f"[Account {account_index + 1}] Fish Points: {data.get('fishPoint', 0)}")
    logger.info(f"[Account {account_index + 1}] EXP: {data.get('exp', 0)}")

def format_time_remaining(milliseconds):
    seconds = int((milliseconds / 1000) % 60)
    minutes = int((milliseconds / (1000 * 60)) % 60)
    hours = int(milliseconds / (1000 * 60 * 60))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

async def check_inventory(session, account):
    account_index = account_states.index(account)
    try:
        async with session.get(f"{config['api_base_url']}/v1/inventory", headers=account["headers"]) as response:
            if response.status == 200:
                data = await response.json()
                account["current_energy"] = data.get("energy", 0)
                return data
            else:
                log_error(f"[Account {account_index + 1}] Failed to check inventory: {response.status}")
                if response.status == 503:
                    log_warn(f"[Account {account_index + 1}] Server temporarily unavailable")
                return None
    except Exception as e:
        log_error(f"[Account {account_index + 1}] Error checking inventory: {str(e)}")
        return None

def select_fishing_range(account):
    account_index = account_states.index(account)
    available_ranges = []
    
    if account["current_energy"] >= config["range_costs"]["long_range"]:
        available_ranges.append("long_range")
    if account["current_energy"] >= config["range_costs"]["mid_range"]:
        available_ranges.append("mid_range")
    if account["current_energy"] >= config["range_costs"]["short_range"]:
        available_ranges.append("short_range")
    
    if not available_ranges:
        log_warn(f"[Account {account_index + 1}] No fishing ranges available with current energy!")
        return "short_range"
    
    selected_range = random.choice(available_ranges)
    if config["fishing_range"] != selected_range:
        config["fishing_range"] = selected_range
        log_info(f"[Account {account_index + 1}] Selected fishing range: {Fore.CYAN}{selected_range} (Cost: {config['range_costs'][selected_range]} energy)")
    
    return selected_range

def interpolate_points(p0, p1, steps):
    pts = []
    for i in range(1, steps):
        t = i / steps
        x = round(p0[0] + (p1[0] - p0[0]) * t)
        y = round(p0[1] + (p1[1] - p0[1]) * t)
        pts.append([x, y])
    return pts

def calculate_position_x(frame, direction):
    return 450 + frame * 2 + direction * 5

def calculate_position_y(frame, direction):
    return 426 + frame * 2 - direction * 3

async def fish(account):
    account_index = account_states.index(account)
    
    async def ws_fishing():
        key_frames = []
        required_frames = 10
        interpolation_steps = 30
        end_sent = False
        game_started = False
        game_success = False
        
        try:
            # Create a separate session for WebSocket connection
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"{config['ws_url']}/?token={account['auth_token']}") as ws:
                    # Send prepare command
                    await ws.send_str(json.dumps({
                        "cmd": "prepare",
                        "range": config["fishing_range"],
                        "is5x": config["is_5x"]
                    }))
                    
                    # Set a timeout for the entire fishing operation
                    start_time = time.time()
                    max_time = 60  # 60 seconds timeout
                    
                    while time.time() - start_time < max_time:
                        try:
                            # Receive message with timeout
                            msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                            
                            # Handle different message types
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                message = json.loads(msg.data)
                                
                                if message.get("type") == "initGame":
                                    game_started = True
                                    await ws.send_str(json.dumps({"cmd": "start"}))
                                
                                elif message.get("type") == "gameState":
                                    frame = message.get("frame", 0)
                                    direction = message.get("dir", 0)
                                    x = calculate_position_x(frame, direction)
                                    y = calculate_position_y(frame, direction)
                                    entry = [x, y, frame, direction] if direction != 0 else [x, y]
                                    key_frames.append(entry)
                                    
                                    if len(key_frames) == required_frames and not end_sent:
                                        final_frames = []
                                        if len(key_frames) < 2:
                                            final_frames = key_frames.copy()
                                        else:
                                            final_frames.append(key_frames[0])
                                            for i in range(1, len(key_frames)):
                                                prev = key_frames[i-1][:2]
                                                curr = key_frames[i][:2]
                                                interpolated = interpolate_points(prev, curr, interpolation_steps)
                                                final_frames.extend(interpolated)
                                                final_frames.append(key_frames[i])
                                        
                                        end_command = {
                                            "cmd": "end",
                                            "rep": {
                                                "fs": 100,
                                                "ns": 200,
                                                "fps": 20,
                                                "frs": final_frames
                                            },
                                            "en": 1
                                        }
                                        await ws.send_str(json.dumps(end_command))
                                        end_sent = True
                                
                                elif message.get("type") == "gameOver":
                                    game_success = message.get("success", False)
                                    if game_success:
                                        fish_info = message["catchedFish"]["fishInfo"]
                                        log_success(f"[Account {account_index + 1}] Successfully caught a {Fore.CYAN}{fish_info['fishName']} (quality: {fish_info['quality']}) worth {fish_info['sellPrice']} coins and {fish_info['expGain']} XP!")
                                        log_info(f"[Account {account_index + 1}] ⭐ Current XP: {message['catchedFish']['currentExp']}/{message['catchedFish']['expToNextLevel']}")
                                        log_highlight(f"[Account {account_index + 1}] ⚡ Remaining Energy", f"{message['catchedFish']['energy']}")
                                        logger.info(f"[Account {account_index + 1}] 💰 Gold: {message['catchedFish']['gold']}")
                                        logger.info(f"[Account {account_index + 1}] 🐟 Fish Points: {message['catchedFish']['fishPoint']}")
                                    else:
                                        log_error(f"[Account {account_index + 1}] Failed to catch fish")
                                        log_highlight(f"[Account {account_index + 1}] ⚡ Remaining Energy", f"{message['catchedFish']['energy']}")
                                        logger.info(f"[Account {account_index + 1}] 💰 Gold: {message['catchedFish']['gold']}")
                                        logger.info(f"[Account {account_index + 1}] 🐟 Fish Points: {message['catchedFish']['fishPoint']}")
                                    
                                    account["current_energy"] = message["catchedFish"]["energy"]
                                    return game_success
                            
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                # Handle binary message - convert to text if possible
                                try:
                                    message = json.loads(msg.data.decode('utf-8'))
                                    # Process the same way as text messages
                                    if message.get("type") == "initGame":
                                        game_started = True
                                        await ws.send_str(json.dumps({"cmd": "start"}))
                                    
                                    # ... other message handling same as above
                                except Exception as e:
                                    log_warn(f"[Account {account_index + 1}] Received binary data but couldn't parse: {str(e)}")
                            
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                log_warn(f"[Account {account_index + 1}] WebSocket connection closed")
                                break
                                
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                log_error(f"[Account {account_index + 1}] WebSocket connection error")
                                break
                                
                        except asyncio.TimeoutError:
                            # This is just a timeout on receive, not the entire operation
                            log_warn(f"[Account {account_index + 1}] Timeout waiting for WebSocket message")
                            continue
                        except Exception as e:
                            log_error(f"[Account {account_index + 1}] Error processing WebSocket message: {str(e)}")
                            continue
                    
                    # If we reach here without returning, it's a timeout
                    if not game_success:
                        log_error(f"[Account {account_index + 1}] Fishing operation timed out after {max_time} seconds")
                        return False
        
        except Exception as e:
            log_error(f"[Account {account_index + 1}] WebSocket connection error: {str(e)}")
            return False
    
    return await ws_fishing()

async def show_energy_countdown(account):
    account_index = account_states.index(account)
    if not account["energy_refresh_time"]:
        return
    
    log_warn(f"[Account {account_index + 1}] Out of energy. Waiting for energy to refresh...")
    
    while datetime.now() < account["energy_refresh_time"]:
        time_remaining = (account["energy_refresh_time"] - datetime.now()).total_seconds() * 1000
        print(f"\r[Account {account_index + 1}] Energy will refresh in: {Fore.CYAN}{format_time_remaining(time_remaining)}", end="")
        await asyncio.sleep(1)
    
    print("\n")
    log_success(f"[Account {account_index + 1}] Energy should be refreshed now!")
    account["energy_refresh_time"] = None
    await asyncio.sleep(5)

async def process_account(session, account):
    account_index = account_states.index(account)
    log_info(f"[Account {account_index + 1}] Starting Fishing Frenzy bot...")
    
    try:
        profile_data = await check_inventory(session, account)
        if not profile_data:
            log_warn(f"[Account {account_index + 1}] Failed to load profile, skipping...")
            return False
        
        display_profile_info(profile_data, account_index)
        
        if account["current_energy"] <= 0:
            if not account["energy_refresh_time"]:
                account["energy_refresh_time"] = datetime.now() + timedelta(hours=config["energy_refresh_hours"])
            await show_energy_countdown(account)
            return False
        
        select_fishing_range(account)
        
        log_info(f"[Account {account_index + 1}] 🎣 Starting fishing attempt with {Fore.CYAN}{config['fishing_range']}... (Energy cost: {config['range_costs'][config['fishing_range']]})")
        success = await fish(account)
        
        if success:
            log_success(f"[Account {account_index + 1}] Fishing attempt completed successfully. Waiting {config['delay_between_fishing']} seconds...")
            await asyncio.sleep(config["delay_between_fishing"])
            account["retry_count"] = 0
            return True
        else:
            account["retry_count"] += 1
            wait_time = config["retry_delay"] * 3 if account["retry_count"] > config["max_retries"] else config["retry_delay"]
            log_warn(f"[Account {account_index + 1}] Fishing attempt failed. Retry {account['retry_count']}/{config['max_retries']}. Waiting {wait_time} seconds...")
            await asyncio.sleep(wait_time)
            return False
    
    except Exception as e:
        log_error(f"[Account {account_index + 1}] Error during fishing attempt: {str(e)}")
        account["retry_count"] += 1
        wait_time = 60 if account["retry_count"] > config["max_retries"] else 10
        log_warn(f"[Account {account_index + 1}] Error occurred. Retry {account['retry_count']}/{config['max_retries']}. Waiting {wait_time} seconds...")
        await asyncio.sleep(wait_time)
        return False

async def batch_fishing(accounts):
    log_info(f"Starting batch fishing with {len(accounts)} accounts...")
    
    async with aiohttp.ClientSession() as session:
        fishing_tasks = []
        
        for account in accounts:
            fishing_tasks.append(process_account(session, account))
        
        results = await asyncio.gather(*fishing_tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False)
        errors = sum(1 for r in results if isinstance(r, Exception))
        
        log_info(f"Batch fishing completed: {successful} successful, {failed} failed, {errors} errors")

async def run_bot():
    display_banner()
    
    # Load tokens and initialize account states
    tokens = load_tokens()
    initialize_account_states(tokens)
    
    log_info('------------------------------------------------------')
    log_info(f"Found {len(account_states)} accounts to process")
    logger.info("Fishing ranges available:")
    logger.info(f"- short_range: {config['range_costs']['short_range']} energy")
    logger.info(f"- mid_range: {config['range_costs']['mid_range']} energy")
    logger.info(f"- long_range: {config['range_costs']['long_range']} energy")
    logger.info(f"Retries: {config['max_retries']}, Delay between fishing: {config['delay_between_fishing']}s")
    logger.info(f"Energy refresh period: {config['energy_refresh_hours']} hours")
    logger.info(f"Account switch delay: {config['account_switch_delay']}s")
    logger.info(f"Concurrent fishing limit: {config['concurrent_fishing_limit']}")
    log_info('------------------------------------------------------')
    
    while True:
        # Group accounts into batches of concurrent_fishing_limit
        batch_size = config["concurrent_fishing_limit"]
        account_batches = [account_states[i:i+batch_size] for i in range(0, len(account_states), batch_size)]
        
        for batch in account_batches:
            await batch_fishing(batch)
            log_info(f"Batch completed. Waiting {config['account_switch_delay']} seconds before next batch...")
            await asyncio.sleep(config["account_switch_delay"])
        
        # Add a small delay before restarting the cycle
        await asyncio.sleep(5)

# Main entry point
if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("\nBot stopped by user")
    except Exception as e:
        log_error(f"Fatal error in bot: {str(e)}")
        log_warn("Bot will restart in 1 minute...")
        time.sleep(60)
        try:
            asyncio.run(run_bot())
        except Exception as e:
>>>>>>> 53c6ac08c3ff49533c085be75e5d2af07a8227f9
            log_error(f"Failed to restart bot: {str(e)}")