import google.generativeai as genai
from typing import List, Dict, Optional, Any
import logging
from src.utils.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GeminiService:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in environment variables")
        
        genai.configure(api_key=settings.GEMINI_API_KEY)
        
        self.model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            generation_config={
                "temperature": settings.GEMINI_TEMPERATURE,
                "top_p": settings.GEMINI_TOP_P,
                "top_k": settings.GEMINI_TOP_K,
                "max_output_tokens": settings.GEMINI_MAX_TOKENS,
            }
        )
        
        self.chat_model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL,
            generation_config={
                "temperature": settings.GEMINI_TEMPERATURE,
                "top_p": settings.GEMINI_TOP_P,
                "top_k": settings.GEMINI_TOP_K,
                "max_output_tokens": settings.GEMINI_MAX_TOKENS,
            }
        )
        
        logger.info(f"Gemini service initialized with model: {settings.GEMINI_MODEL}")
    
    async def generate_response(
        self,
        prompt: str,
        context: Optional[List[Dict[str, str]]] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        try:
            if context:
                chat = self.chat_model.start_chat(history=self._format_chat_history(context))
                
                if system_prompt:
                    full_prompt = f"{system_prompt}\n\nUser: {prompt}"
                else:
                    full_prompt = prompt
                
                response = chat.send_message(full_prompt)
            else:
                if system_prompt:
                    full_prompt = f"{system_prompt}\n\nUser: {prompt}\n\nAssistant:"
                else:
                    full_prompt = f"User: {prompt}\n\nAssistant:"
                
                response = self.model.generate_content(full_prompt)
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise Exception(f"Failed to generate response: {str(e)}")
    
    async def generate_summary(self, text: str, max_points: int = 5) -> str:
        try:
            prompt = f"""
            Please provide a concise summary of the following conversation.
            Include up to {max_points} key points or topics discussed.
            
            Conversation:
            {text}
            
            Summary:
            """
            
            response = self.model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            raise Exception(f"Failed to generate summary: {str(e)}")
    
    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        try:
            prompt = f"""
            Analyze the sentiment of the following text.
            Provide:
            1. Overall sentiment (positive/negative/neutral)
            2. Confidence score (0-1)
            3. Key emotions detected
            4. Brief explanation
            
            Text: {text}
            
            Respond in JSON format.
            """
            
            response = self.model.generate_content(prompt)
            
            import json
            try:
                result = json.loads(response.text)
            except:
                result = {
                    "sentiment": "neutral",
                    "confidence": 0.5,
                    "emotions": [],
                    "explanation": response.text
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return {
                "sentiment": "unknown",
                "confidence": 0,
                "emotions": [],
                "explanation": str(e)
            }
    
    async def extract_entities(self, text: str) -> List[Dict[str, str]]:
        try:
            prompt = f"""
            Extract named entities from the following text.
            Include: people, organizations, locations, dates, products, etc.
            
            Text: {text}
            
            Return as a JSON list with objects containing 'entity', 'type', and 'context'.
            """
            
            response = self.model.generate_content(prompt)
            
            import json
            try:
                entities = json.loads(response.text)
            except:
                entities = []
            
            return entities
            
        except Exception as e:
            logger.error(f"Error extracting entities: {e}")
            return []
    
    async def generate_suggestions(self, context: str, user_query: str) -> List[str]:
        try:
            prompt = f"""
            Based on the conversation context and the user's latest message,
            provide 3-5 relevant follow-up questions or suggestions.
            
            Context: {context}
            User's message: {user_query}
            
            Provide suggestions as a numbered list.
            """
            
            response = self.model.generate_content(prompt)
            
            suggestions = []
            for line in response.text.split('\n'):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith('-')):
                    suggestion = line.lstrip('0123456789.-) ').strip()
                    if suggestion:
                        suggestions.append(suggestion)
            
            return suggestions[:5]
            
        except Exception as e:
            logger.error(f"Error generating suggestions: {e}")
            return []
    
    def _format_chat_history(self, context: List[Dict[str, str]]) -> List[Dict[str, str]]:
        formatted_history = []
        
        for message in context:
            role = message.get("role", "user")
            content = message.get("content", "")
            
            if role == "user":
                formatted_history.append({
                    "role": "user",
                    "parts": [content]
                })
            elif role == "assistant":
                formatted_history.append({
                    "role": "model",
                    "parts": [content]
                })
        
        return formatted_history
    
    async def moderate_content(self, text: str) -> Dict[str, Any]:
        try:
            prompt = f"""
            Analyze the following text for inappropriate content.
            Check for: harassment, hate speech, violence, adult content, etc.
            
            Text: {text}
            
            Respond with:
            - is_safe: boolean
            - categories: list of detected issues
            - severity: low/medium/high
            """
            
            response = self.model.generate_content(prompt)
            
            import json
            try:
                result = json.loads(response.text)
            except:
                result = {
                    "is_safe": True,
                    "categories": [],
                    "severity": "low"
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error moderating content: {e}")
            return {
                "is_safe": True,
                "categories": [],
                "severity": "unknown",
                "error": str(e)
            }