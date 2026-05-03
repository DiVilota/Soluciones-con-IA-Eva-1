import streamlit as st
from src.core import chat_hardibot_stream_sync

# Configuración de la página
st.set_page_config(page_title="HardiBot", page_icon="🤖", layout="centered")
st.title("🤖 HardiBot")
st.caption("Tu Consultor Experto en Hardware Computacional (Duoc UC Edition)")

# Inicializar el historial de chat en la memoria de Streamlit
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "¡Hola! Soy HardiBot. ¿Qué tipo de PC necesitas armar hoy?",
        }
    ]

# Renderizar los mensajes del historial
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Capturar el input del usuario
if prompt := st.chat_input("Escribe tu consulta aquí..."):
    # Mostrar el mensaje del usuario en pantalla
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Mostrar la respuesta del bot en streaming
    with st.chat_message("assistant"):
        # st.write_stream consume el generador que hicimos en core.py
        response = st.write_stream(chat_hardibot_stream_sync(prompt))

    # Guardar la respuesta final en el historial
    st.session_state.messages.append({"role": "assistant", "content": response})
