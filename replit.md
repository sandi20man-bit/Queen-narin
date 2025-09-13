# Replit.md

## Overview

This is a Telegram bot designed for daily attendance tracking. The bot provides automated attendance management functionality through Telegram's messaging platform, allowing users to track their daily presence/absence status. The application uses Python with the python-telegram-bot library to handle Telegram API interactions and includes timezone support for accurate time-based operations.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Bot Framework Architecture
The application is built on the python-telegram-bot library (version 20.3), utilizing the modern async/await pattern with the ApplicationBuilder. The bot implements a command-based interface with callback query handling for interactive buttons and menus.

### Configuration Management
The system uses a dual-layer configuration approach:
- Primary: Environment variables loaded from a .env file using python-dotenv
- Fallback: Direct system environment variables
- Includes automatic .env template generation for easy setup
- Configuration validation for critical parameters like CHAT_ID and TIMEZONE

### Command Structure
The bot implements handlers for:
- CommandHandler: For processing slash commands
- CallbackQueryHandler: For handling inline keyboard interactions
- Structured around attendance management workflows

### Time Zone Handling
Uses pytz library for robust timezone management with Asia/Jakarta as the default timezone. Includes timezone validation to prevent configuration errors.

### Error Handling and Validation
Implements comprehensive validation for:
- Bot token verification
- Chat ID format validation (integer conversion)
- Timezone string validation against pytz database
- Graceful fallbacks for invalid configurations

## External Dependencies

### Telegram Bot API
- **Service**: Telegram Bot API via python-telegram-bot library
- **Purpose**: Core messaging platform and user interface
- **Integration**: Direct API communication for sending/receiving messages and handling callbacks

### Python Libraries
- **python-telegram-bot (20.3)**: Main framework for Telegram bot functionality
- **pytz (2025.2)**: Timezone handling and datetime operations
- **python-dotenv (1.1.1)**: Environment variable management from .env files

### Environment Configuration
- **BOT_TOKEN**: Required Telegram bot authentication token
- **CHAT_ID**: Target chat/group identifier for bot operations
- **TIMEZONE**: Configurable timezone setting (defaults to Asia/Jakarta)