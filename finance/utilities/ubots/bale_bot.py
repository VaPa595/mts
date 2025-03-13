import asyncio

import telegram


class BaleBot:
    def __init__(self, token: str, base_url="https://tapi.bale.ai/"):
        self.bot = telegram.Bot(token=token, base_url=base_url)
        self.last_message_id = None

    async def send_message(self, chat_id: str, text: str, msg_id_to_delete=None, delete_last_msg=False):
        try:
            if msg_id_to_delete is not None:
                await self.delete_message(chat_id, msg_id_to_delete)
            if delete_last_msg is True:
                await self.delete_last_message(chat_id)

            a = await self.bot.sendMessage(chat_id=chat_id, text=text)
            self.last_message_id = a.message_id
            # print(f"Sent_Msg_To_Bale: {text}")
            # print(type(a.message_id))
            # print(a.message_id)
            return a.message_id
        except Exception as e:
            print("**BaleBot_Exception: " + str(e))
            return None  # is necessary

    async def delete_last_message(self, chat_id: str):
        await self.delete_message(chat_id, self.last_message_id)

    async def delete_message(self, chat_id, msg_id):
        if msg_id is not None:  # for the first time
            try:
                await self.bot.deleteMessage(chat_id=chat_id, message_id=msg_id)
            except (telegram.error.BadRequest, telegram.error.NetworkError) as e:
                print("**BaleBot_Exception: " + str(e))
    # async def run_async_method(self, method):
    #
    #     # Run an async method in an event loop
    #     loop = asyncio.get_event_loop()
    #     task = loop.create_task(method)
    #     await task


#################################
# def __init__(self, token: str, base_url="https://tapi.bale.ai/"):
#     self.bot = telegram.Bot(token=token, base_url=base_url)
#     self.last_message_id = None
#
#     self.loop = asyncio.new_event_loop()

# def send_message(self, chat_id: str, text: str, msg_id_to_delete=None, delete_last_msg=False):
#     if msg_id_to_delete is not None:
#         self.delete_message(chat_id, msg_id_to_delete)
#     if delete_last_msg is True:
#         self.delete_last_message(chat_id)
#     asyncio.set_event_loop(self.loop)  # todo (1), it should be here, otherwise makes exception in another frxstreamsnew.py
#     a = self.loop.run_until_complete(self.bot.sendMessage(chat_id=chat_id, text=text))
#     self.last_message_id = a.message_id
#     # print(type(a.message_id))
#     print(a.message_id)
#     return a.message_id
#
# def delete_last_message(self, chat_id: str):
#     self.delete_message(chat_id, self.last_message_id)
#
# def delete_message(self, chat_id, msg_id):
#     if msg_id is not None:  # for the first time
#         try:
#             self.loop.run_until_complete(self.bot.deleteMessage(chat_id=chat_id, message_id=msg_id))
#         except (telegram.error.BadRequest, telegram.error.NetworkError) as e:
#             print("**BaleBot_Exception: " + str(e))


# Send a message to the created bot () then see the following link (including token of the bot: (i.e. 'bot'+token)):
# https://tapi.bale.ai/bot793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8/getupdates

# if you send a message from inside the Bale to this bot. In the above link you find the message. The chat id in this message belongs to this bot.
# ... if you use this chat id to send a message via send_message method, the message is sent to this bot (it will be shown after your previous message)
# if you want to send a message via send_message to a Bale group, you should first add the bot into the group. To do this, you need to add the bot to your contacts.
# ... Not the bot user name ends with (bot, Bot). Then you have to send a message (in English :D) to that group and then use the above link to find new message and get that chat id as
# ... the id of the group.

# in above '793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8' is the token (793045610 is the user_id of the bot, but also is part of the token)
# I used same token (bot) for two groups.
# also you can find information in the following link:
# https://tapi.bale.ai/bot793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8/getme

if __name__ == '__main_':
    tmpbot = BaleBot(token='793045610:OowHfbYw9aji7Hk8OKRptf5wRgLoG5shnpVSbbB8')
    # tmpbot.send_message(chat_id='4426980252', text="Wellcome Abbbbas/Saleh")
    tmpbot.send_message(chat_id='6183990665', text="Wellcome Abbbbas/Saleh")
