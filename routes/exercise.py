from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from dotenv import load_dotenv
from models import User
from utils import get_current_user
from database import get_db
load_dotenv()


exercise_router = APIRouter()

# 운동 프로그램 가져오기
@exercise_router.get('/get_training_program')
def get_user_train_programs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

        training_data = []
        for program in user.training_programs:
            cycles = [
                {"day_index": cycle.day_index, "exercise_type": cycle.exercise_type}
                for cycle in program.cycles
            ]

            exercise_sets = []
            for ex_set in program.exercise_sets:
                details = [
                    {
                        "name": detail.name,
                        "sets": detail.sets,
                        "reps": detail.reps,
                        "unit": detail.unit,
                        "weight_type": detail.weight_type,
                        "weight_value": detail.weight_value,
                        "rest": detail.rest
                    }
                    for detail in ex_set.details
                ]

                exercise_sets.append({
                    "set_key": ex_set.set_key,
                    "focus_area": ex_set.focus_area,
                    "details": details
                })

            training_data.append({
                "program_id": program.id,
                "training_cycle_length": program.training_cycle_length,
                "goals": program.goals,
                "constraints": program.constraints,
                "notes": program.notes,
                "cycles": cycles,
                "exercise_sets": exercise_sets
            })

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "훈련 프로그램을 성공적으로 가져왔습니다.",
                "training_data": training_data
            }
        )

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"데이터베이스 오류가 발생했습니다: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"예상치 못한 오류가 발생했습니다: {str(e)}")

# JSON 형태 : 
# {
#   "name": "training_program_recommendation",
#   "strict": true,
#   "schema": {
#     "type": "object",
#     "properties": {
#       "training_cycle_length": {
#         "type": "integer",
#         "description": "The length of the training cycle in days."
#       },
#       "goals": {
#         "type": "object",
#         "description": "The goals associated with the training program.",
#         "properties": {
#           "goal_type": {
#             "type": "string",
#             "description": "The type of fitness goal (e.g., strength, endurance)."
#           },
#           "target": {
#             "type": "string",
#             "description": "The specific target for the goal (e.g., weight loss target, muscle gain)."
#           }
#         },
#         "required": [
#           "goal_type",
#           "target"
#         ],
#         "additionalProperties": false
#       },
#       "constraints": {
#         "type": "object",
#         "description": "Constraints or limitations regarding the training program.",
#         "properties": {
#           "injuries": {
#             "type": "string",
#             "description": "Any injuries to consider in the training plan."
#           },
#           "equipment": {
#             "type": "string",
#             "description": "Equipment available to the user."
#           }
#         },
#         "required": [
#           "injuries",
#           "equipment"
#         ],
#         "additionalProperties": false
#       },
#       "notes": {
#         "type": "string",
#         "description": "Additional notes or comments regarding the training program."
#       },
#       "created_at": {
#         "type": "string",
#         "description": "The timestamp when the training program was created."
#       },
#       "cycles": {
#         "type": "array",
#         "description": "The training cycles associated with the program.",
#         "items": {
#           "type": "object",
#           "properties": {
#             "cycle_id": {
#               "type": "integer",
#               "description": "The unique identifier for the training cycle."
#             },
#             "day_index": {
#               "type": "integer",
#               "description": "The index of the day in the training cycle."
#             },
#             "exercise_type": {
#               "type": "integer",
#               "description": "The type of exercise for this training cycle."
#             },
#             "sets": {
#               "type": "array",
#               "description": "The exercise sets associated with this cycle.",
#               "items": {
#                 "type": "object",
#                 "properties": {
#                   "set_id": {
#                     "type": "integer",
#                     "description": "The unique identifier for the exercise set."
#                   },
#                   "focus_area": {
#                     "type": "string",
#                     "description": "The area of focus for the exercise set."
#                   },
#                   "exercises": {
#                     "type": "array",
#                     "description": "The details of exercises contained in this set.",
#                     "items": {
#                       "type": "object",
#                       "properties": {
#                         "exercise_id": {
#                           "type": "integer",
#                           "description": "The unique identifier for the exercise."
#                         },
#                         "name": {
#                           "type": "string",
#                           "description": "The name of the exercise."
#                         },
#                         "sets": {
#                           "type": "integer",
#                           "description": "Number of sets for the exercise."
#                         },
#                         "reps": {
#                           "type": "integer",
#                           "description": "Number of repetitions for each set."
#                         },
#                         "unit": {
#                           "type": "string",
#                           "description": "The unit of measurement (e.g., kg, lbs)."
#                         },
#                         "weight_type": {
#                           "type": "string",
#                           "description": "Type of weight (e.g., free weight, machine)."
#                         },
#                         "weight_value": {
#                           "type": "number",
#                           "description": "The weight value for the exercise."
#                         },
#                         "rest": {
#                           "type": "integer",
#                           "description": "Rest time in seconds between sets."
#                         }
#                       },
#                       "required": [
#                         "exercise_id",
#                         "name",
#                         "sets",
#                         "reps",
#                         "unit",
#                         "weight_type",
#                         "weight_value",
#                         "rest"
#                       ],
#                       "additionalProperties": false
#                     }
#                   }
#                 },
#                 "required": [
#                   "set_id",
#                   "focus_area",
#                   "exercises"
#                 ],
#                 "additionalProperties": false
#               }
#             }
#           },
#           "required": [
#             "cycle_id",
#             "day_index",
#             "exercise_type",
#             "sets"
#           ],
#           "additionalProperties": false
#         }
#       }
#     },
#     "required": [
#       "training_cycle_length",
#       "goals",
#       "constraints",
#       "notes",
#       "created_at",
#       "cycles"
#     ],
#     "additionalProperties": false
#   }
# }