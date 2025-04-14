# 🎣 Fishing Frenzy Auto Bot

An automated fishing bot for [Fishing Frenzy](https://fishingfrenzy.co/) that intelligently manages energy and fishing ranges.

## ✨ Features

- **Energy-Aware Fishing**: Automatically selects fishing ranges based on available energy
- **24/7 Operation**: Continuous fishing with automatic retry system
- **Energy Tracking**: Monitors energy levels and waits for refresh when depleted
- **Detailed Logging**: Comprehensive console logs with color-coded status updates
- **Error Handling**: Robust error recovery and connection management

## 📋 Requirements

- Node.js (v14 or higher)
- Valid Fishing Frenzy authentication token

## 🚀 Installation

1. Clone the repository:
```bash
git clone https://github.com/airdropinsiders/FishingFrenzy-Auto-Bot.git
cd FishingFrenzy-Auto-Bot
```

2. Install dependencies:
```bash
npm install
```

3. Create a `token.txt` file in the root directory and paste your Fishing Frenzy authentication token:
```bash
echo "YOUR_TOKEN_HERE" > token.txt
```

## 💻 Usage

Start the bot:
```bash
npm start
```

## ⚙️ Configuration

You can customize the bot's behavior by modifying the configuration variables in `index.js`:

```javascript
const config = {
  authToken: authToken,
  apiBaseUrl: 'https://api.fishingfrenzy.co',
  wsUrl: 'wss://api.fishingfrenzy.co',
  fishingRange: 'mid_range', // default: mid_range
  is5x: false,
  delayBetweenFishing: 5000,
  retryDelay: 30000,
  maxRetries: 5,
  energyRefreshHours: 24, // Energy refreshes every 24 hours
  // Energy cost for each fishing range
  rangeCosts: {
    'short_range': 1,
    'mid_range': 2,
    'long_range': 3
  }
};
```

## 📊 Energy Management

The bot intelligently selects fishing ranges based on your available energy:
- `short_range`: Costs 1 energy
- `mid_range`: Costs 2 energy
- `long_range`: Costs 3 energy

When energy is depleted, the bot will wait for the energy refresh time (default: 24 hours).

## 🔒 Authentication

To obtain your authentication token:
1. Log in to [Fishing Frenzy](https://fishingfrenzy.co/)
2. Open browser developer tools (F12)
3. Go to Application tab → Local Storage → fishingfrenzy.co
4. Copy the token value (without quotes)
5. Paste it into your `token.txt` file

## Pre-requisites for setup.js:

Create a WalletX.json and fill it with
```json
  {
    "address": "YOUR_ADDRESS",
    "privateKey": "YOUR_PRIVATE_KEY"
  }
```
Fill it as much as you want

## ⚠️ Disclaimer

This bot is provided for educational purposes only. Use of automated scripts may violate Fishing Frenzy's terms of service. Use at your own risk.

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📧 Contact

For questions or support, please open an issue on the GitHub repository.
