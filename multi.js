const axios = require('axios');
const WebSocket = require('ws');
const chalk = require('chalk');
const fs = require('fs');

// Read tokens from file into an array
let authTokens;
try {
  authTokens = fs.readFileSync('tokens.txt', 'utf8')
    .split('\n')
    .map(token => token.trim())
    .filter(token => token.length > 0);
  if (authTokens.length === 0) throw new Error('No valid tokens found');
} catch (error) {
  console.error(' Failed to read token.txt:', error.message);
  process.exit(1);
}

const config = {
  apiBaseUrl: 'https://api.fishingfrenzy.co',
  wsUrl: 'wss://api.fishingfrenzy.co',
  fishingRange: 'mid_range',
  is5x: false,
  delayBetweenFishing: 5000,
  retryDelay: 30000,
  maxRetries: 5,
  // energyRefreshHours: 0.1,
  rangeCosts: {
    'short_range': 1,
    'mid_range': 2,
    'long_range': 3
  },
  accountSwitchDelay: 10000 // Delay between switching accounts in ms
};

// Account-specific data
const accountStates = authTokens.map(token => ({
  authToken: token,
  currentEnergy: 0,
  retryCount: 0,
  energyRefreshTime: null,
  headers: {
    'accept': 'application/json',
    'accept-language': 'en-US,en;q=0.6',
    'authorization': `Bearer ${token}`,
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
}));

const log = (msg) => console.log(msg);
const logSuccess = (msg) => console.log(chalk.green(`${msg}`));
const logInfo = (msg) => console.log(`${msg}`);
const logWarn = (msg) => console.log(chalk.yellow(`${msg}`));
const logError = (msg) => console.log(chalk.red(`${msg}`));
const logHighlight = (label, value) => console.log(`${label}: ${chalk.cyan(value)}`);

function displayBanner() {
  const banner = [
    chalk.cyan('=================================================='),
    chalk.cyan('    Fishing Frenzy Auto Bot - Airdrop Insiders    '),
    chalk.cyan('==================================================')
  ];
  banner.forEach(line => console.log(line));
}

function displayProfileInfo(data, accountIndex) {
  logSuccess(`[Account ${accountIndex + 1}] Profile Loaded Successfully!`);
  logInfo(`[Account ${accountIndex + 1}] User ID: ${data.userId || 'N/A'}`);
  log(`[Account ${accountIndex + 1}] Gold: ${data.gold || 0}`);
  logHighlight(`[Account ${accountIndex + 1}] Energy`, `${data.energy || 0}`);
  log(`[Account ${accountIndex + 1}] Fish Points: ${data.fishPoint || 0}`);
  log(`[Account ${accountIndex + 1}] EXP: ${data.exp || 0}`);
}

function formatTimeRemaining(milliseconds) {
  const seconds = Math.floor(milliseconds / 1000) % 60;
  const minutes = Math.floor(milliseconds / (1000 * 60)) % 60;
  const hours = Math.floor(milliseconds / (1000 * 60 * 60));
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

async function checkInventory(account) {
  try {
    const response = await axios.get(`${config.apiBaseUrl}/v1/inventory`, { headers: account.headers });
    account.currentEnergy = response.data.energy || 0;
    return response.data;
  } catch (error) {
    logError(`[Account ${authTokens.indexOf(account.authToken) + 1}] Failed to check inventory: ${error.message}`);
    if (error.response && error.response.status === 503) {
      logWarn(`[Account ${authTokens.indexOf(account.authToken) + 1}] Server temporarily unavailable`);
    }
    return null;
  }
}

function selectFishingRange(account) {
  const availableRanges = [];
  if (account.currentEnergy >= config.rangeCosts['long_range']) availableRanges.push('long_range');
  if (account.currentEnergy >= config.rangeCosts['mid_range']) availableRanges.push('mid_range');
  if (account.currentEnergy >= config.rangeCosts['short_range']) availableRanges.push('short_range');
  
  if (availableRanges.length === 0) {
    logWarn(`[Account ${authTokens.indexOf(account.authToken) + 1}] No fishing ranges available with current energy!`);
    return 'short_range';
  }
  const selectedRange = availableRanges[Math.floor(Math.random() * availableRanges.length)];
  if (config.fishingRange !== selectedRange) {
    config.fishingRange = selectedRange;
    logInfo(`[Account ${authTokens.indexOf(account.authToken) + 1}] Selected fishing range: ${chalk.cyan(config.fishingRange)} (Cost: ${config.rangeCosts[config.fishingRange]} energy)`);
  }
  return selectedRange;
}

function interpolatePoints(p0, p1, steps) {
  const pts = [];
  for (let i = 1; i < steps; i++) {
    const t = i / steps;
    const x = Math.round(p0[0] + (p1[0] - p0[0]) * t);
    const y = Math.round(p0[1] + (p1[1] - p0[1]) * t);
    pts.push([x, y]);
  }
  return pts;
}

function calculatePositionX(frame, direction) {
  return 450 + frame * 2 + direction * 5;
}

function calculatePositionY(frame, direction) {
  return 426 + frame * 2 - direction * 3;
}

async function fish(account) {
  return new Promise((resolve, reject) => {
    let wsConnection = null;
    let gameStarted = false;
    let gameSuccess = false;
    const keyFrames = [];
    const requiredFrames = 10;
    const interpolationSteps = 30;
    let endSent = false;
    const accountIndex = authTokens.indexOf(account.authToken) + 1;

    wsConnection = new WebSocket(`${config.wsUrl}/?token=${account.authToken}`);

    const timeout = setTimeout(() => {
      logWarn(`[Account ${accountIndex}] Fishing timeout - closing connection`);
      if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
        wsConnection.close();
      }
      resolve(false);
    }, 60000);

    wsConnection.on('open', () => {
      wsConnection.send(JSON.stringify({
        cmd: 'prepare',
        range: config.fishingRange,
        is5x: config.is5x
      }));
    });

    wsConnection.on('message', (data) => {
      try {
        const message = JSON.parse(data.toString());

        if (message.type === 'initGame') {
          gameStarted = true;
          wsConnection.send(JSON.stringify({ cmd: 'start' }));
        }

        if (message.type === 'gameState') {
          const frame = message.frame || 0;
          const direction = message.dir || 0;
          const x = calculatePositionX(frame, direction);
          const y = calculatePositionY(frame, direction);
          let entry = direction !== 0 ? [x, y, frame, direction] : [x, y];
          keyFrames.push(entry);

          if (keyFrames.length === requiredFrames && !endSent) {
            let finalFrames = [];
            if ( keyFrames.length < 2) {
              finalFrames = keyFrames.slice();
            } else {
              finalFrames.push(keyFrames[0]);
              for (let i = 1; i < keyFrames.length; i++) {
                const prev = keyFrames[i - 1].slice(0, 2);
                const curr = keyFrames[i].slice(0, 2);
                const interpolated = interpolatePoints(prev, curr, interpolationSteps);
                finalFrames.push(...interpolated);
                finalFrames.push(keyFrames[i]);
              }
            }

            const endCommand = {
              cmd: 'end',
              rep: {
                fs: 100,
                ns: 200,
                fps: 20,
                frs: finalFrames
              },
              en: 1
            };
            wsConnection.send(JSON.stringify(endCommand));
            endSent = true;
          }
        }

        if (message.type === 'gameOver') {
          gameSuccess = message.success;
          if (gameSuccess) {
            const fish = message.catchedFish.fishInfo;
            logSuccess(`[Account ${accountIndex}] Successfully caught a ${chalk.cyan(fish.fishName)} (quality: ${fish.quality}) worth ${fish.sellPrice} coins and ${fish.expGain} XP!`);
            logInfo(`[Account ${accountIndex}] ⭐ Current XP: ${message.catchedFish.currentExp}/${message.catchedFish.expToNextLevel}`);
            logHighlight(`[Account ${accountIndex}] ⚡ Remaining Energy`, `${message.catchedFish.energy}`);
            log(`[Account ${accountIndex}] 💰 Gold: ${message.catchedFish.gold}`);
            log(`[Account ${accountIndex}] 🐟 Fish Points: ${message.catchedFish.fishPoint}`);
            account.currentEnergy = message.catchedFish.energy;
          } else {
            logError(`[Account ${accountIndex}] Failed to catch fish`);
            logHighlight(`[Account ${accountIndex}] ⚡ Remaining Energy`, `${message.catchedFish.energy}`);
            log(`[Account ${accountIndex}] 💰 Gold: ${message.catchedFish.gold}`);
            log(`[Account ${accountIndex}] 🐟 Fish Points: ${message.catchedFish.fishPoint}`);
            account.currentEnergy = message.catchedFish.energy;
          }
          clearTimeout(timeout);
          wsConnection.close();
          resolve(gameSuccess);
        }
      } catch (parseError) {
        logError(`[Account ${accountIndex}] Error parsing message: ${parseError.message}`);
      }
    });

    wsConnection.on('error', (error) => {
      logError(`[Account ${accountIndex}] WebSocket error: ${error.message}`);
      clearTimeout(timeout);
      reject(error);
    });

    wsConnection.on('close', () => {
      if (!gameStarted) {
        logError(`[Account ${accountIndex}] Connection closed before fishing started`);
        resolve(false);
      }
      clearTimeout(timeout);
    });
  });
}

async function showEnergyCountdown(account) {
  const accountIndex = authTokens.indexOf(account.authToken) + 1;
  if (!account.energyRefreshTime) return;
  logWarn(`[Account ${accountIndex}] Out of energy. Waiting for energy to refresh...`);
  while (new Date() < account.energyRefreshTime) {
    const timeRemaining = account.energyRefreshTime - new Date();
    process.stdout.write(`\r[Account ${accountIndex}] Energy will refresh in: ${chalk.cyan(formatTimeRemaining(timeRemaining))}`);
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  console.log('\n');
  logSuccess(`[Account ${accountIndex}] Energy should be refreshed now!`);
  account.energyRefreshTime = null;
  await new Promise(resolve => setTimeout(resolve, 5000));
}

async function runAccount(account) {
    const accountIndex = authTokens.indexOf(account.authToken) + 1;
    logInfo(`[Account ${accountIndex}] Starting Fishing Frenzy bot...`);
    
    try {
      const profileData = await checkInventory(account);
      if (!profileData) {
        logWarn(`[Account ${accountIndex}] Failed to load profile, skipping...`);
        return;
      }
      
      displayProfileInfo(profileData, authTokens.indexOf(account.authToken));
  
      if (account.currentEnergy <= 0) {
        if (!account.energyRefreshTime) {
          account.energyRefreshTime = new Date();
          account.energyRefreshTime.setHours(account.energyRefreshTime.getHours() + config.energyRefreshHours);
        }
        await showEnergyCountdown(account);
        return; // Exit the function instead of continuing
      }
  
      selectFishingRange(account);
  
      logInfo(`[Account ${accountIndex}] 🎣 Starting fishing attempt with ${chalk.cyan(config.fishingRange)}... (Energy cost: ${config.rangeCosts[config.fishingRange]})`);
      const success = await fish(account);
  
      if (success) {
        logSuccess(`[Account ${accountIndex}] Fishing attempt completed successfully. Waiting ${config.delayBetweenFishing / 1000} seconds...`);
        await new Promise(resolve => setTimeout(resolve, config.delayBetweenFishing));
        account.retryCount = 0;
      } else {
        account.retryCount++;
        const waitTime = account.retryCount > config.maxRetries ? config.retryDelay * 3 : config.retryDelay;
        logWarn(`[Account ${accountIndex}] Fishing attempt failed. Retry ${account.retryCount}/${config.maxRetries}. Waiting ${waitTime / 1000} seconds...`);
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }
    } catch (error) {
      logError(`[Account ${accountIndex}] Error during fishing attempt: ${error.message}`);
      account.retryCount++;
      const waitTime = account.retryCount > config.maxRetries ? 60000 : 10000;
      logWarn(`[Account ${accountIndex}] Error occurred. Retry ${account.retryCount}/${config.maxRetries}. Waiting ${waitTime / 1000} seconds...`);
      await new Promise(resolve => setTimeout(resolve, waitTime));
    }
  }
  
  async function runBot() {
    displayBanner();
    logInfo('------------------------------------------------------');
    logInfo(`Found ${authTokens.length} accounts to process`);
    log(`Fishing ranges available:`);
    log(`- short_range: ${config.rangeCosts['short_range']} energy`);
    log(`- mid_range: ${config.rangeCosts['mid_range']} energy`);
    log(`- long_range: ${config.rangeCosts['long_range']} energy`);
    log(`Retries: ${config.maxRetries}, Delay between fishing: ${config.delayBetweenFishing}ms`);
    log(`Energy refresh period: ${config.energyRefreshHours} hours`);
    log(`Account switch delay: ${config.accountSwitchDelay}ms`);
    logInfo('------------------------------------------------------');
  
    while (true) {
      for (const account of accountStates) {
        const accountIndex = authTokens.indexOf(account.authToken) + 1;
        logInfo(`[Account ${accountIndex}] Processing account...`);
        await runAccount(account);
        logInfo(`[Account ${accountIndex}] Finished processing. Waiting ${config.accountSwitchDelay / 1000} seconds before next account...`);
        await new Promise(resolve => setTimeout(resolve, config.accountSwitchDelay));
      }
      // Add a small delay before restarting the cycle
      await new Promise(resolve => setTimeout(resolve, 5000));
    }
  }

process.on('uncaughtException', (error) => {
  logError(`Uncaught exception: ${error}`);
  logWarn('Bot will restart in 1 minute...');
  setTimeout(() => runBot(), 60000);
});

runBot().catch(error => {
  logError(`Fatal error in bot: ${error}`);
  process.exit(1);
});