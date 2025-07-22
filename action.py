from prompt_dict import prompt_dict
from ai_generator import AIGenerator
from database import Database
import json

class Action:
    def __init__(self):
        self.instructionType = None
        self.ai_generator = AIGenerator()
        self.db = Database()

    def take_action(self, instruction_type, transcript, id):
        instruction_type = instruction_type.strip()
        self.instructionType = instruction_type
        if instruction_type == "CREATE_PROFILE":
            prompt = f"""{prompt_dict.get("BREED_AGE_PROMPT")} {transcript}"""
            response_text = self.ai_generator.generate_response(prompt)
            try:
                name_breed_age = json.loads(response_text)
            except json.JSONDecodeError:
                name_breed_age = {"name": None, "breed": None, "age": None}
            if not name_breed_age["name"] and name_breed_age["breed"] and not name_breed_age["age"]:
                return "Please provide your pet's breed and age."
            elif not name_breed_age["name"]:
                return "What is your pet's name?"
            elif not name_breed_age["breed"]:
                return "What is your pet's breed?"
            elif not name_breed_age["age"]:
                return "How old is your pet?"
            else:
                pet_data = {
                    'name': name_breed_age["name"],
                    'owner': id,
                    'breed': name_breed_age["breed"],
                    'age': name_breed_age["age"],
                }
                inserted = self.db.insert_data("pet_profile", pet_data)
                if inserted:
                    return "Profile Created Successfully"
                else:
                    return "Trouble creating pet profile"
        elif instruction_type == "CARE_ROUTINE":
            # Extract care routine information using AI
            prompt = f"""{prompt_dict.get("CARE_ROUTINE_PROMPT", "Extract care routine information including pet name, care type, description, frequency, and time from:")} {transcript}"""
            response_text = self.ai_generator.generate_response(prompt)

            try:
                care_info = json.loads(response_text)
            except json.JSONDecodeError:
                care_info = {"pet_name": None, "care_type": None, "description": None, "frequency": None,
                             "time_of_day": None}

            # Validate required fields
            if not care_info.get("pet_name"):
                return "Please specify which pet this care routine is for."
            if not care_info.get("care_type"):
                return "Please specify the type of care routine (feeding, walking, grooming, etc.)."
            if not care_info.get("frequency"):
                return "Please specify how often this should be done (daily, weekly, etc.)."

            # Get pet ID from pet name
            pet_data = self.db.get_pet_by_name(care_info["pet_name"], id)
            if not pet_data:
                return f"No pet profile found for {care_info['pet_name']}. Please create a profile first."

            pet_id = pet_data[0]  # Assuming ID is first column

            # Prepare notification data
            notification_data = {
                'pet_id': pet_id,
                'care_type': care_info["care_type"],
                'description': care_info.get("description", ""),
                'frequency': care_info["frequency"],
                'time_of_day': care_info.get("time_of_day"),
                'is_active': True
            }

            # Insert notification
            inserted = self.db.insert_data("notifications", notification_data, user_context=id)
            if inserted:
                return f"Care routine set up successfully for {care_info['pet_name']}: {care_info['care_type']} - {care_info['frequency']}"
            else:
                return "Trouble setting up care routine"

        elif instruction_type == "HEALTH":
            prompt = f"""{prompt_dict.get("HEALTH_EXTRACT_PROMPT", "Extract pet health query information:")} {transcript}"""
            extract_response = self.ai_generator.generate_response(prompt)

            try:
                health_info = json.loads(extract_response)
            except json.JSONDecodeError:
                health_info = {"pet_name": None, "query_category": "general", "symptoms": None}

            # Validate pet name
            pet_data = None
            pet_id = None
            pet_name = health_info.get("pet_name")

            if pet_name:
                pet_data = self.db.get_pet_by_name(pet_name)
                if pet_data:
                    pet_id = pet_data[0]  # Assuming ID is first column
                else:
                    return f"No pet profile found for {pet_name}. Please create a profile first for more personalized advice."

            # Generate health response with pet context
            health_prompt = self._build_health_prompt(health_info, pet_data, transcript)
            health_response = self.ai_generator.generate_response(health_prompt)

            # Create response summary for logging (first 500 chars)
            response_summary = health_response[:500] + "..." if len(health_response) > 500 else health_response

            # Log the health query in the logs table
            health_log_data = {
                "query_text": transcript,
                "pet_name": pet_name or "Unknown",
                "pet_id": pet_id,
                "query_category": health_info.get("query_category", "general"),
                "response_summary": response_summary,
                "urgency": health_info.get("urgency", "low")
            }

            self.db.log_operation(
                table_name="health_queries",
                operation="QUERY",
                record_id=pet_id,
                data_after=health_log_data,
                user_context=id
            )

            return health_response
        elif instruction_type == "GENERAL":
            # TODO: Implement general queries
            return "General pet advice feature coming soon!"

        else:
            return "I don't understand that instruction type. Please try CREATE_PROFILE or CARE_ROUTINE."

    def _build_health_prompt(self, health_info, pet_data, original_transcript):
        """Build a comprehensive health prompt with pet context"""
        base_prompt = prompt_dict.get("HEALTH_RESPONSE_PROMPT", "Provide pet health advice for:")

        # Add pet context if available
        pet_context = ""
        if pet_data:
            pet_name = pet_data[1] if len(pet_data) > 1 else "the pet"
            pet_breed = pet_data[2] if len(pet_data) > 2 else "Unknown breed"
            pet_age = pet_data[3] if len(pet_data) > 3 else "Unknown age"
            pet_context = f"\nPet Profile: {pet_name} is a {pet_breed}, {pet_age} years old."

        # Add query categorization
        category_context = f"\nQuery Category: {health_info.get('query_category', 'general')}"

        # Add symptoms if extracted
        symptoms_context = ""
        if health_info.get("symptoms"):
            symptoms_context = f"\nObserved Symptoms: {health_info.get('symptoms')}"

        full_prompt = f"""{base_prompt}
    {pet_context}
    {category_context}
    {symptoms_context}

    User Query: {original_transcript}

    Please provide helpful, accurate pet health information. Always recommend consulting with a veterinarian for serious concerns or emergencies."""

        return full_prompt