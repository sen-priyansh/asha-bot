import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_TOKENS, TEMPERATURE, TOP_P, TOP_K

# Configure the Gemini API
genai.configure(api_key=GEMINI_API_KEY)

class GeminiAI:
    def __init__(self):
        try:
            # Configure the model
            generation_config = {
                "temperature": TEMPERATURE,
                "top_p": TOP_P,
                "top_k": TOP_K,
                "max_output_tokens": MAX_TOKENS,
            }

            # Initialize the model
            self.model = genai.GenerativeModel(
                model_name=GEMINI_MODEL,
                generation_config=generation_config
            )
            
            # Test the model availability
            self.model.generate_content("Test")
            
        except Exception as e:
            print(f"Error initializing Gemini AI: {e}")
            print("Falling back to gemini-pro model...")
            # Fall back to the standard model
            self.model = genai.GenerativeModel(
                model_name="gemini-pro",
                generation_config=generation_config
            )
        
        # Chat history for each user
        self.chat_sessions = {}
    
    async def get_response(self, user_id, message):
        """
        Get a response from the Gemini AI model
        
        Args:
            user_id (str): The user's ID to maintain conversation history
            message (str): The user's message
            
        Returns:
            str: The AI's response
        """
        try:
            # Create a new chat session if one doesn't exist for this user
            if user_id not in self.chat_sessions:
                chat = self.model.start_chat(history=[])
                # Set the context for the chat
                chat.send_message(
                    "You are a helpful Discord bot assistant. You are friendly, concise, and helpful. "
                    "You should respond in a conversational manner while being respectful and appropriate for all ages."
                )
                self.chat_sessions[user_id] = chat
            
            # Get the chat session for this user
            chat = self.chat_sessions[user_id]
            
            # Generate a response
            response = chat.send_message(message)
            
            # Return the text response
            return response.text
            
        except Exception as e:
            # Handle any errors
            print(f"Error in Gemini AI: {e}")
            return f"I'm sorry, I encountered an error: {str(e)}"
    
    def reset_chat(self, user_id):
        """
        Reset the chat history for a user
        
        Args:
            user_id (str): The user's ID
        """
        if user_id in self.chat_sessions:
            del self.chat_sessions[user_id]
            return True
        return False 