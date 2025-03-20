from telethon import TelegramClient, events, Button, functions, types
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError
)
import asyncio
import nest_asyncio
from telethon.sync import TelegramClient as SyncTelegramClient

# Apply nest_asyncio
nest_asyncio.apply()

# Configuration
API_ID = '25832801'
API_HASH = 'a87d2e2d87303042bc95c2ebbba304b1'
BOT_TOKEN = '8159885107:AAGHJyvF6NT8o5WXojiDlK_pxmmoeoY6drU'
# SOURCE_CHANNEL can be a public username (e.g., '@Dhol_Ullu_Originals') or private channel (invite or ID) that the user is a member of
SOURCE_CHANNEL = -1001879580266  
DESTINATION_CHANNEL = '@testinggggg6666'

class UserSession:
    def __init__(self):
        self.phone = None
        self.phone_code_hash = None
        self.step = 'phone'
        self.attempts = 0

class MessageForwarder:
    def __init__(self, client, source_channel, destination_channel):
        self.client = client
        self.source_channel = source_channel
        self.destination_channel = destination_channel
        self.last_message_id = None
        self.is_running = False
        self.source_entity = None
        self.destination_entity = None

    async def start_forwarding(self):
        self.is_running = True
        try:
            # Get channel entities (works for both public and private channels)
            self.source_entity = await self.client.get_entity(self.source_channel)
            self.destination_entity = await self.client.get_entity(self.destination_channel)
            
            # Get last message ID from source channel
            messages = await self.client.get_messages(self.source_entity, limit=1)
            if messages:
                self.last_message_id = messages[0].id

            print(f"Starting forwarding from {self.source_channel} to {self.destination_channel}")
            print(f"Last message ID: {self.last_message_id}")

            while self.is_running:
                try:
                    # Get new messages since last checked message
                    messages = await self.client.get_messages(
                        self.source_entity, 
                        min_id=self.last_message_id
                    )
                    for message in reversed(messages):
                        try:
                            # Forward the message
                            await self.client.send_message(self.destination_entity, message)
                            print(f"Forwarded message ID: {message.id}")
                            self.last_message_id = max(self.last_message_id or 0, message.id)
                        except Exception as e:
                            print(f"Error forwarding message {message.id}: {str(e)}")
                except Exception as e:
                    print(f"Error getting messages: {str(e)}")
                await asyncio.sleep(5)  # Check every 5 seconds

        except Exception as e:
            print(f"Forwarding error: {str(e)}")

    def stop_forwarding(self):
        self.is_running = False

# Initialize clients
bot = TelegramClient('bot', API_ID, API_HASH)
client = TelegramClient('session_name', API_ID, API_HASH)
auth_users = {}
forwarder = None

def register_handlers():
    @bot.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        await event.respond('Welcome! Click the button below to start authentication.',
                          buttons=Button.inline('Begin Authentication', b'auth'))

    @bot.on(events.CallbackQuery(data=b'auth'))
    async def auth_handler(event):
        auth_users[event.sender_id] = UserSession()
        await event.respond('Please send your phone number (including country code, e.g., +1234567890)')

    @bot.on(events.NewMessage)
    async def message_handler(event):
        if not event.text:
            return

        user_id = event.sender_id
        if user_id not in auth_users:
            return

        session = auth_users[user_id]
        try:
            if session.step == 'phone':
                phone = event.text.strip()
                try:
                    if not client.is_connected():
                        await client.connect()
                    
                    # Send code request for user authentication
                    result = await client(functions.auth.SendCodeRequest(
                        phone_number=phone,
                        api_id=int(API_ID),
                        api_hash=API_HASH,
                        settings=types.CodeSettings(
                            allow_flashcall=False,
                            current_number=True,
                            allow_app_hash=True,
                            allow_missed_call=False
                        )
                    ))
                    
                    session.phone = phone
                    session.phone_code_hash = result.phone_code_hash
                    session.step = 'code'
                    
                    await event.respond(
                        "Please check for an OTP in your official Telegram account.\n"
                        "If OTP is `12345`, **please send it as** `1 2 3 4 5`\n\n"
                        "Enter /cancel to cancel the process"
                    )
                except Exception as e:
                    print(f"Debug - Error details: {str(e)}")
                    await event.respond(f'Error sending code: {str(e)}. Please try again.')
                    del auth_users[user_id]

            elif session.step == 'code':
                if event.text.strip() == '/cancel':
                    await event.respond('Process cancelled!')
                    del auth_users[user_id]
                    return

                if not client.is_connected():
                    await client.connect()
                    
                code = event.text.strip().replace(" ", "")
                try:
                    await client(functions.auth.SignInRequest(
                        phone_number=session.phone,
                        phone_code_hash=session.phone_code_hash,
                        phone_code=code
                    ))
                    await start_forwarding()
                    await event.respond('Successfully logged in! Forwarding service is active.')
                    del auth_users[user_id]
                except SessionPasswordNeededError:
                    session.step = '2fa'
                    await event.respond('Two-factor authentication is enabled. Please enter your password:')
                except PhoneCodeInvalidError:
                    await event.respond('Invalid code. Please try again.')
                except PhoneCodeExpiredError:
                    await event.respond('Code expired. Please start over with /start')
                    del auth_users[user_id]
                except Exception as e:
                    await event.respond(f'Error during login: {str(e)}')
                    session.attempts += 1
                    if session.attempts >= 3:
                        del auth_users[user_id]
                        await event.respond('Too many attempts. Please start over with /start')

            elif session.step == '2fa':
                if not client.is_connected():
                    await client.connect()
                try:
                    await client.sign_in(password=event.text.strip())
                    await start_forwarding()
                    await event.respond('Successfully logged in with 2FA! Forwarding service is active.')
                    del auth_users[user_id]
                except Exception as e:
                    await event.respond(f'Invalid 2FA password: {str(e)}')
                    session.attempts += 1
                    if session.attempts >= 3:
                        del auth_users[user_id]
                        await event.respond('Too many attempts. Please start over with /start')

        except Exception as e:
            await event.respond(f'An error occurred: {str(e)}\nPlease start over with /start')
            del auth_users[user_id]

async def start_forwarding():
    global forwarder
    try:
        # Create new forwarder instance; this works for both public and private source channels
        forwarder = MessageForwarder(client, SOURCE_CHANNEL, DESTINATION_CHANNEL)
        
        # Start forwarding in background
        asyncio.create_task(forwarder.start_forwarding())
        
        print("Bot is running!")
        print(f"Monitoring {SOURCE_CHANNEL}")
        print(f"Forwarding to {DESTINATION_CHANNEL}")
    except Exception as e:
        print(f"Error starting forwarder: {str(e)}")

async def main():
    try:
        await bot.start(bot_token=BOT_TOKEN)
        await client.connect()
        
        # Register handlers
        register_handlers()
        
        if await client.is_user_authorized():
            await start_forwarding()
        else:
            print("Waiting for authentication through bot...")
            print("Please start the bot and complete authentication.")
        
        # Run bot until disconnected
        await bot.run_until_disconnected()
    except Exception as e:
        print(f"Main loop error: {str(e)}")
    finally:
        if forwarder:
            forwarder.stop_forwarding()
        await client.disconnect()
        await bot.disconnect()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Error occurred: {str(e)}")
