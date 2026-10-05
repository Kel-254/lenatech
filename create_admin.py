from werkzeug.security import generate_password_hash

import sqlite3


username = "admin"

password = "Lenatechs@254"


hashed_password = generate_password_hash(
    password
)


connection = sqlite3.connect(
    "lena_techs.db"
)


connection.execute(
    """
    INSERT INTO admins
    (username, password)

    VALUES (?, ?)
    """,
    (
        username,
        hashed_password
    )
)


connection.commit()

connection.close()


print("Admin account created successfully.")