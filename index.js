const axios = require('axios');
const WebSocket = require('ws');
const chalk = require('chalk');
const fs = require('fs');

let authToken;
try {
  authToken = fs.readFileSync('token.txt', 'utf8').trim();
} catch (error) {
  console.error(' Failed to read token.txt:', error.message);
  process.exit(1);
}

const config = {
  authToken: authToken,
  apiBaseUrl: 'https://api.fishingfrenzy.co',
  wsUrl: 'wss://api.fishingfrenzy.co',
  fishingRange: 'long_range', 
  is5x: false,
  delayBetweenFishing: 5000,
  retryDelay: 30000,
  maxRetries: 5,
  energyRefreshHours: 24, 
  rangeCosts: {
    'short_range': 1,
    'mid_range': 2,
    'long_range': 3
  }
};

const headers = {
  'accept': 'application/json',
  'accept-language': 'en-US,en;q=0.6',
  'authorization': `Bearer ${config.authToken}`, 
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
};

let currentEnergy = 0;
let retryCount = 0;
let energyRefreshTime = null;

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

function displayProfileInfo(data) {
  logSuccess('Profile Loaded Successfully!');
  logInfo(` User ID: ${data.userId || 'N/A'}`); 
  log(` Gold: ${data.gold || 0}`); 
  logHighlight(' Energy', `${data.energy || 0}`); 
  log(` Fish Points: ${data.fishPoint || 0}`); 
  log(` EXP: ${data.exp || 0}`); 
}

function formatTimeRemaining(milliseconds) {
  const seconds = Math.floor(milliseconds / 1000) % 60;
  const minutes = Math.floor(milliseconds / (1000 * 60)) % 60;
  const hours = Math.floor(milliseconds / (1000 * 60 * 60));
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`; 
}

async function checkInventory() {
  try {
    const response = await axios.get(`${config.apiBaseUrl}/v1/inventory`, { headers }); 
    currentEnergy = response.data.energy || 0;
    displayProfileInfo(response.data);

    if (currentEnergy > 0) {
      return true;
    } else {
      if (!energyRefreshTime) {
        energyRefreshTime = new Date();
        energyRefreshTime.setHours(energyRefreshTime.getHours() + config.energyRefreshHours);
      }
      return false;
    }
  } catch (error) {
    logError(`Failed to check inventory: ${error.message}`); 
    if (error.response && error.response.status === 503) {
      logWarn('Server temporarily unavailable, waiting before retry...');
    }
    return false;
  }
}

function selectFishingRange() {
  const availableRanges = [];
  if (currentEnergy >= config.rangeCosts['long_range']) {
    availableRanges.push('long_range');
  }
  if (currentEnergy >= config.rangeCosts['mid_range']) {
    availableRanges.push('mid_range');
  }
  if (currentEnergy >= config.rangeCosts['short_range']) {
    availableRanges.push('short_range');
  }
  if (availableRanges.length === 0) {
    logWarn("No fishing ranges available with current energy!");
    return 'short_range';
  }
  const selectedRange = availableRanges[Math.floor(Math.random() * availableRanges.length)];
  if (config.fishingRange !== selectedRange) {
    config.fishingRange = selectedRange;
    logInfo(`Selected fishing range: ${chalk.cyan(config.fishingRange)} (Cost: ${config.rangeCosts[config.fishingRange]} energy)`); 
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

async function fish() {
  return new Promise((resolve, reject) => {
    let wsConnection = null;
    let gameStarted = false;
    let gameSuccess = false;
    const keyFrames = [];
    const requiredFrames = 10;
    const interpolationSteps = 30;
    let endSent = false;

    wsConnection = new WebSocket(`${config.wsUrl}/?token=${config.authToken}`); 

    const timeout = setTimeout(() => {
      logWarn('Fishing timeout - closing connection');
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
            if (keyFrames.length < 2) {
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
            logSuccess(`Successfully caught a ${chalk.cyan(fish.fishName)} (quality: ${fish.quality}) worth ${fish.sellPrice} coins and ${fish.expGain} XP!`); 
            logInfo(`⭐ Current XP: ${message.catchedFish.currentExp}/${message.catchedFish.expToNextLevel}`); 
            logHighlight(`⚡ Remaining Energy`, `${message.catchedFish.energy}`); 
            log(`💰 Gold: ${message.catchedFish.gold}`); 
            log(`🐟 Fish Points: ${message.catchedFish.fishPoint}`); 
            
            currentEnergy = message.catchedFish.energy;
          } else {
            logError('Failed to catch fish');
            logHighlight(`⚡ Remaining Energy`, `${message.catchedFish.energy}`); 
            log(`💰 Gold: ${message.catchedFish.gold}`); 
            log(`🐟 Fish Points: ${message.catchedFish.fishPoint}`); 
            
            currentEnergy = message.catchedFish.energy;
          }
          clearTimeout(timeout);
          wsConnection.close();
          resolve(gameSuccess);
        }
      } catch (parseError) {
        logError(`Error parsing message: ${parseError.message}`); 
      }
    });

    wsConnection.on('error', (error) => {
      logError(`WebSocket error: ${error.message}`); 
      clearTimeout(timeout);
      reject(error);
    });

    wsConnection.on('close', () => {
      if (!gameStarted) {
        logError('Connection closed before fishing started');
        resolve(false);
      }
      clearTimeout(timeout);
    });
  });
}

async function showEnergyCountdown() {
  if (!energyRefreshTime) return;
  logWarn('Out of energy. Waiting for energy to refresh...');
  while (new Date() < energyRefreshTime) {
    const timeRemaining = energyRefreshTime - new Date();
    process.stdout.write(`\r Energy will refresh in: ${chalk.cyan(formatTimeRemaining(timeRemaining))}`); 
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  console.log('\n');
  logSuccess('Energy should be refreshed now!');
  energyRefreshTime = null;
  await new Promise(resolve => setTimeout(resolve, 5000));
}

async function runBot() {
  logInfo('Starting Fishing Frenzy bot...');
  while (true) {
    try {
      const hasEnergy = await checkInventory();

      if (!hasEnergy) {
        await showEnergyCountdown();
        continue;
      }

      selectFishingRange();

      logInfo(`🎣 Starting fishing attempt with ${chalk.cyan(config.fishingRange)}... (Energy cost: ${config.rangeCosts[config.fishingRange]})`); 
      const success = await fish();

      if (success) {
        logSuccess(`Fishing attempt completed successfully. Waiting ${config.delayBetweenFishing / 1000} seconds...`); 
        await new Promise(resolve => setTimeout(resolve, config.delayBetweenFishing));
        retryCount = 0;
      } else {
        retryCount++;
        const waitTime = retryCount > config.maxRetries ? config.retryDelay * 3 : config.retryDelay;
        logWarn(`Fishing attempt failed. Retry ${retryCount}/${config.maxRetries}. Waiting ${waitTime / 1000} seconds...`); 
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }
    } catch (error) {
      logError(`Error during fishing attempt: ${error.message}`); 
      retryCount++;
      const waitTime = retryCount > config.maxRetries ? 60000 : 10000;
      logWarn(`Error occurred. Retry ${retryCount}/${config.maxRetries}. Waiting ${waitTime / 1000} seconds...`); 
      await new Promise(resolve => setTimeout(resolve, waitTime));
    }
  }
}

process.on('uncaughtException', (error) => {
  logError(`Uncaught exception: ${error}`); 
  logWarn('Bot will restart in 1 minute...');
  setTimeout(() => runBot(), 60000);
});

displayBanner(); 
logInfo('------------------------------------------------------');
log(`Fishing ranges available:`); 
log(`- short_range: ${config.rangeCosts['short_range']} energy`); 
log(`- mid_range: ${config.rangeCosts['mid_range']} energy`); 
log(`- long_range: ${config.rangeCosts['long_range']} energy`); 
log(`Retries: ${config.maxRetries}, Delay between fishing: ${config.delayBetweenFishing}ms`); 
log(`Energy refresh period: ${config.energyRefreshHours} hours`); 
logInfo('------------------------------------------------------');
runBot().catch(error => {
  logError(`Fatal error in bot: ${error}`); 
  process.exit(1);
});