# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /code

# Copy requirements and install dependencies
COPY ./backend/requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Copy the backend and frontend directories into the container
COPY ./backend /code/backend
COPY ./frontend /code/frontend

# Create the temp_uploads directory and set permissions
RUN mkdir -p /code/backend/temp_uploads && chmod 777 /code/backend/temp_uploads

# Set the working directory to backend to run the app
WORKDIR /code/backend

# Expose port 7860 (Hugging Face Spaces expects port 7860)
EXPOSE 7860

# Command to run the FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
