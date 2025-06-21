        // --- DOM Elements ---
        const userInput = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const chatContainer = document.getElementById('chat-container');
        const welcomeScreen = document.getElementById('welcome-screen');
        const newChatBtn = document.getElementById('newChatBtn');
        const sidebar = document.getElementById('sidebar');
        const toggleSidebarBtn = document.getElementById('toggleSidebarBtn');
        const toggleSidebarIcon = document.getElementById('toggleSidebarIcon');
        const sidebarContent = document.getElementById('sidebarContent');
        const sidebarLabels = document.querySelectorAll('.sidebar-label');
        let sidebarCollapsed = false;
        const thinkToggle = document.getElementById('thinkToggle');
        const newsToggle = document.getElementById('newsToggle');
        const searchToggle = document.getElementById('searchToggle');
        const weatherToggle = document.getElementById('weatherToggle');
        const fetchToggle = document.getElementById('fetchToggle');
        const xPostToggle = document.getElementById('xPostToggle');
        const pcToggle = document.getElementById('pcToggle');

        // --- State Variables ---
        let conversationHistory = [];
        let apiEndpoint = ''; // Fetched from server
        let modelName = ''; // Fetched from server
        let weatherMcpUrl = ''; // Fetched from server
        let sessionId = "session-" + Date.now() + "-" + Math.random().toString(36).substring(2);
        
        
        // --- INITIALIZATION ---
        document.addEventListener('DOMContentLoaded', async () => {
            await loadConfig();
            initializeSidebar();
            sendBtn.disabled = true;
            userInput.focus();

            // --- Event Listeners ---
            sendBtn.addEventListener('click', sendMessage);
            
            userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if(!sendBtn.disabled) sendMessage();
                }
            });

            userInput.addEventListener('input', () => {
                userInput.style.height = 'auto';
                userInput.style.height = (userInput.scrollHeight) + 'px';
                const hasTextInput = userInput.value.trim() !== '';
                sendBtn.disabled = !hasTextInput || (!apiEndpoint && !weatherMcpUrl);
            });

            newChatBtn.addEventListener('click', () => {
                conversationHistory = [];
                chatContainer.innerHTML = '';
                chatContainer.appendChild(welcomeScreen);
                welcomeScreen.style.display = 'flex';
                userInput.value = '';
                sendBtn.disabled = true;
                sessionId = "session-" + Date.now() + "-" + Math.random().toString(36).substring(2);
                console.log("New chat started. New Session ID:", sessionId);
            });

            
            toggleSidebarBtn.addEventListener('click', () => {
                sidebarCollapsed = !sidebarCollapsed;
                if (sidebarCollapsed) {
                    sidebar.style.width = '3.5rem';
                    sidebarContent.style.opacity = '0';
                    sidebarContent.style.pointerEvents = 'none';
                    sidebarContent.style.visibility = 'hidden';
                    sidebar.classList.add('items-center'); // Center everything vertically
                    toggleSidebarIcon.classList.remove('fa-bars');
                    toggleSidebarIcon.classList.add('fa-arrow-right');
                    sidebarLabels.forEach(lbl => lbl.style.display = 'none');
                } else {
                    sidebar.style.width = '16rem';
                    sidebarContent.style.opacity = '1';
                    sidebarContent.style.pointerEvents = 'auto';
                    sidebarContent.style.visibility = 'visible';
                    sidebar.classList.remove('items-center');
                    toggleSidebarIcon.classList.remove('fa-arrow-right');
                    toggleSidebarIcon.classList.add('fa-bars');
                    sidebarLabels.forEach(lbl => lbl.style.display = 'inline');
                }
            });

            [newsToggle, searchToggle, weatherToggle, fetchToggle, xPostToggle, pcToggle].forEach(toggle => {
                toggle.addEventListener('click', () => {
                    toggle.classList.toggle('selected');

                    // Force thinkToggle ON
                    thinkToggle.checked = true;
                    thinkToggle.disabled = true; // prevent user from toggling it off
                });
            });

            window.addEventListener('resize', initializeSidebar);
        });

        // --- CORE FUNCTIONS ---
        
        async function loadConfig() {
            try {
                const response = await fetch('/config');
                if (!response.ok) throw new Error('Failed to fetch server configuration.');
                const config = await response.json();
                apiEndpoint = config.apiEndpoint;
                modelName = config.modelName;
                weatherMcpUrl = config.weatherMcpUrl; // Keep this in case other parts need it, but it's no longer used for the direct call
                console.log('Configuration loaded:', { apiEndpoint, modelName, weatherMcpUrl });
            } catch (error) {
                console.error('Error loading config:', error);
                chatContainer.innerHTML = `<div class="max-w-4xl mx-auto p-4 md:p-6"><p class="text-red-400"><strong>Configuration Error:</strong> Could not load settings from the server. Please ensure the Flask server is running correctly.</p></div>`;
            }
        }

        // --- FIX START: Simplified sendMessage to always use the LLM ---
        async function sendMessage() {
            const userMessage = userInput.value.trim();
            if (userMessage === '') return;

            if (welcomeScreen.style.display !== 'none') {
                welcomeScreen.style.display = 'none';
            }

            userInput.value = '';
            userInput.style.height = 'auto';
            sendBtn.disabled = true;

            // Always send the request to the LLM. The LLM will decide if it needs to use a tool.
            await getLLMResponse(userMessage);
        }
        // --- FIX END ---

        // --- FIX START: Modified getLLMResponse to pass tool permissions ---
        async function getLLMResponse(userMessage) {
            let processedMessage = userMessage;
            
            // Build a list of permissions based on the toggles to send to the LLM
            const permissions = [];
            if (newsToggle.classList.contains('selected')) {
                permissions.push('/use_news');
            }
            if (searchToggle.classList.contains('selected')) {
                permissions.push('/use_search');
            }
            if (weatherToggle.classList.contains('selected')) {
                permissions.push('/use_weather');
            }
            // --- NEW: Logic for the fetch toggle ---
            if (fetchToggle.classList.contains('selected')) {
                permissions.push('/use_fetch');
            }
            if (xPostToggle.classList.contains('selected')) {
                permissions.push('/use_xpost');
            }
            if (pcToggle.classList.contains('selected')) {
                permissions.push('/use_pc');
            }

            if (thinkToggle.checked) {
                permissions.push('/think');
            } else {
                permissions.push('/no_think');
            }

            // Append all permissions to the message string that will be processed by the backend.
            if(permissions.length > 0) {
                processedMessage += " " + permissions.join(' ');
            }
            
            // Append the original, clean user message to the UI
            appendMessage(userMessage, 'user');
            
            // Append the processed message (with permissions) to the history for the LLM
            conversationHistory.push({ role: 'user', content: processedMessage });
            
            const botMessageContainer = appendMessage('', 'bot', true);
            const thinkingContainer = botMessageContainer.querySelector('.thinking-container');
            const thinkingContentEl = botMessageContainer.querySelector('.thinking-content');
            const responseContentEl = botMessageContainer.querySelector('.response-content');
            const typingIndicator = botMessageContainer.querySelector('.typing-indicator');

            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ messages: conversationHistory }),
                });

                if (!response.ok) {
                    // If the response is not OK (e.g., 400 or 500 error), handle it here.
                    let errorMsg = `Server error! Status: ${response.status}`;
                    try {
                        // Try to get the specific error message from the server's JSON response
                        const errorData = await response.json();
                        if (errorData && errorData.error) {
                            errorMsg = errorData.error; // Use the specific error from app.py
                        }
                    } catch (e) {
                        // Could not parse JSON, so we stick with the generic HTTP status error.
                        console.error("Could not parse error JSON from server.", e);
                    }
                    // Throw the specific error so it can be caught and displayed in the UI.
                    throw new Error(errorMsg);
                }
                
                // If response is OK, proceed with streaming the content as before
                if(typingIndicator) typingIndicator.remove();
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n').filter(line => line.trim() !== '');

                    for (const line of lines) {
                         if (line.startsWith('data: ')) {
                             const jsonStr = line.substring(6);
                             if (jsonStr === '[DONE]') break;
                             try {
                                 const data = JSON.parse(jsonStr);
                                 const content = data.choices[0]?.delta?.content || '';
                                 if (content) {
                                     fullResponse += content;
                                 }
                             } catch (e) {
                                 console.error('Error parsing stream data:', e);
                             }
                         }
                    }
                    
                    let unprocessedResponse = fullResponse;
                    let thinkingText = '';
                    
                    const completedThinkRegex = /<think>([\s\S]*?)<\/think>/g;
                    let match;
                    
                    completedThinkRegex.lastIndex = 0;
                    while ((match = completedThinkRegex.exec(unprocessedResponse)) !== null) {
                        thinkingText += match[1] + '\n\n';
                    }

                    let responseText = unprocessedResponse.replace(completedThinkRegex, '');
                    const openThinkTagIndex = responseText.lastIndexOf('<think>');

                    if (openThinkTagIndex !== -1) {
                        thinkingText += responseText.substring(openThinkTagIndex + '<think>'.length);
                        responseText = responseText.substring(0, openThinkTagIndex);
                    }
                    
                    if (thinkingText.trim()) {
                        thinkingContainer.classList.remove('hidden');
                        thinkingContentEl.innerHTML = marked.parse(thinkingText);
                    }
                    
                    responseContentEl.innerHTML = marked.parse(responseText.trim());

                    updateCodeBlocks();
                    chatContainer.scrollTop = chatContainer.scrollHeight;
                }
                
                const finalThinkTagRegex = /<think>([\s\S]*?)<\/think>/g;
                const finalResponseText = fullResponse.replace(finalThinkTagRegex, '').trim();
                conversationHistory.push({ role: 'assistant', content: finalResponseText });
                updateCodeBlocks();

            } catch (error) {
                // This block now catches all errors, including our specific, thrown ones.
                console.error('An error occurred in getLLMResponse:', error);
                
                // Display the specific error message in the bot's response container.
                if (responseContentEl) {
                     responseContentEl.innerHTML = `<p class="text-red-400"><strong>Error:</strong> ${error.message}</p>`;
                }
                if(typingIndicator) typingIndicator.remove();
            }

        }
        // --- FIX END ---

        // --- FIX START: Removed the now-unused getWeather function ---
        // The getWeather function is no longer needed as the LLM will handle tool calls.
        // --- FIX END ---
        
        function appendMessage(content, role, isLoading = false) {
            const messageWrapper = document.createElement('div');
            messageWrapper.className = `w-full ${role === 'user' ? 'message-user' : 'message-bot'}`;
            
            const messageContainer = document.createElement('div');
            messageContainer.className = 'max-w-4xl mx-auto p-4 md:p-6 flex items-start space-x-4';

            const icon = document.createElement('div');
            icon.className = 'w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-white';
            icon.innerHTML = role === 'user' 
                ? `<i class="fas fa-user"></i>`
                : `<i class="fas fa-robot"></i>`;
            icon.classList.add(role === 'user' ? 'bg-indigo-500' : 'bg-teal-500');

            const contentWrapper = document.createElement('div');
            contentWrapper.className = 'flex-grow min-w-0';

            if (role === 'bot') {
                contentWrapper.innerHTML = `
                    <div class="thinking-container hidden">
                        <details>
                            <summary class="cursor-pointer flex items-center justify-between">
                                <span>Show thinking</span>
                                <i class="fas fa-chevron-down transform transition-transform"></i>
                            </summary>
                            <div class="thinking-content prose prose-invert max-w-none"></div>
                        </details>
                    </div>
                    <div class="response-content prose prose-invert max-w-none mt-2"></div>
                `;
                const responseContentEl = contentWrapper.querySelector('.response-content');
                 if (isLoading) {
                      responseContentEl.innerHTML = '<div class="typing-indicator"><span>.</span><span>.</span><span>.</span></div>';
                      const style = document.createElement('style');
                      style.textContent = `
                          .typing-indicator span { animation: blink 1.4s infinite both; }
                          .typing-indicator span:nth-child(2) { animation-delay: .2s; }
                          .typing-indicator span:nth-child(3) { animation-delay: .4s; }
                          @keyframes blink { 0% { opacity: .2; } 20% { opacity: 1; } 100% { opacity: .2; } }
                      `;
                      document.head.appendChild(style);
                 }
                const details = contentWrapper.querySelector('details');
                details.addEventListener('toggle', (event) => {
                    const icon = event.currentTarget.querySelector('summary i');
                    icon.classList.toggle('rotate-180');
                });
            } else {
                 const messageContent = document.createElement('div');
                 messageContent.className = 'prose prose-invert max-w-none';
                 messageContent.innerHTML = marked.parse(content);
                 contentWrapper.appendChild(messageContent);
            }
            
            messageContainer.appendChild(icon);
            messageContainer.appendChild(contentWrapper);
            messageWrapper.appendChild(messageContainer);
            chatContainer.appendChild(messageWrapper);
            chatContainer.scrollTop = chatContainer.scrollHeight;

            if (role !== 'user' && !isLoading) {
                 updateCodeBlocks();
            }
            return messageWrapper;
        }
        
        function updateCodeBlocks() {
            document.querySelectorAll('pre').forEach((pre) => {
                if (pre.querySelector('.copy-btn')) return;

                const code = pre.querySelector('code');
                if (code) hljs.highlightElement(code);

                const copyBtn = document.createElement('button');
                copyBtn.className = 'copy-btn';
                copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy';
                copyBtn.addEventListener('click', () => {
                    const codeToCopy = code ? code.innerText : pre.innerText;
                    const textArea = document.createElement("textarea");
                    textArea.value = codeToCopy;
                    document.body.appendChild(textArea);
                    textArea.select();
                    try {
                        document.execCommand('copy');
                        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
                    } catch (err) {
                        console.error('Failed to copy text: ', err);
                        copyBtn.textContent = 'Failed!';
                    }
                    document.body.removeChild(textArea);

                    setTimeout(() => { copyBtn.innerHTML = '<i class="fas fa-copy"></i> Copy'; }, 2000);
                });
                pre.appendChild(copyBtn);
            });
        }
        
        function initializeSidebar() {
            if (window.innerWidth < 768) {
                sidebar.classList.add('-translate-x-full');
                toggleSidebarIcon.className = 'fas fa-bars';
            } else {
                sidebar.classList.remove('-translate-x-full');
            }
        }
