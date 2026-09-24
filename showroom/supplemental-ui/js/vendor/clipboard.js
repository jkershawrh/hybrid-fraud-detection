(function () {
  'use strict'

  const TRAILING_SPACE_RX = / +$/gm
  const supportsCopy = window.navigator.clipboard || document.queryCommandSupported('copy')

  Array.from(document.querySelectorAll('.doc .listingblock pre.highlight')).forEach(function (pre) {
    const code = pre.querySelector('code')
    if (!code) return

    const toolbox = document.createElement('div')
    toolbox.className = 'source-toolbox'
    if (code.dataset.lang) {
      const lang = document.createElement('span')
      lang.className = 'source-lang'
      lang.textContent = code.dataset.lang
      toolbox.appendChild(lang)
    }

    if (supportsCopy) {
      const copy = document.createElement('button')
      copy.className = 'copy-button'
      copy.title = 'Copy to clipboard'
      copy.setAttribute('aria-label', 'Copy to clipboard')
      copy.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true" class="copy-icon"><path fill-rule="evenodd" d="M5.75 1a.75.75 0 00-.75.75v3c0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75v-3a.75.75 0 00-.75-.75h-4.5zm.75 3V2.5h3V4h-3zm-2.874-.467a.75.75 0 00-.752-1.298A1.75 1.75 0 002 3.75v9.5c0 .966.784 1.75 1.75 1.75h8.5A1.75 1.75 0 0014 13.25v-9.5a1.75 1.75 0 00-.874-1.515.75.75 0 10-.752 1.298.25.25 0 01.126.217v9.5a.25.25 0 01-.25.25h-8.5a.25.25 0 01-.25-.25v-9.5a.25.25 0 01.126-.217z"></path></svg><span class="copy-toast">Copied!</span>'
      copy.addEventListener('click', writeToClipboard.bind(copy, code))
      toolbox.appendChild(copy)
    }

    const listingblock = pre.closest('.listingblock')
    if (listingblock && (listingblock.classList.contains('execute') || listingblock.classList.contains('execute-top'))) {
      toolbox.appendChild(makeExecuteButton(code, 'top'))
    }
    if (listingblock && listingblock.classList.contains('execute-bottom')) {
      toolbox.appendChild(makeExecuteButton(code, 'bottom'))
    }
    pre.parentNode.appendChild(toolbox)
  })

  function makeExecuteButton (code, target) {
    const button = document.createElement('button')
    button.className = 'paste-button'
    const label = target === 'bottom' ? 'Run in secondary terminal' : 'Run in terminal'
    button.title = label
    button.setAttribute('aria-label', label)
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true" class="paste-icon"><path d="M9.25 12a.75.75 0 0 1-.22.53l-2.75 2.75a.75.75 0 0 1-1.06-1.06L7.44 12 5.22 9.78a.75.75 0 1 1 1.06-1.06l2.75 2.75c.141.14.22.331.22.53Zm2 2a.75.75 0 0 0 0 1.5h5a.75.75 0 0 0 0-1.5h-5Z"></path><path d="M0 4.75C0 3.784.784 3 1.75 3h20.5c.966 0 1.75.784 1.75 1.75v14.5A1.75 1.75 0 0 1 22.25 21H1.75A1.75 1.75 0 0 1 0 19.25Zm1.75-.25a.25.25 0 0 0-.25.25v14.5c0 .138.112.25.25.25h20.5a.25.25 0 0 0 .25-.25V4.75a.25.25 0 0 0-.25-.25Z"></path></svg><span class="paste-toast">Executed!</span>'
    if (target === 'bottom') {
      const marker = document.createElement('span')
      marker.className = 'paste-label'
      marker.textContent = '2'
      button.appendChild(marker)
    }
    button.addEventListener('click', pasteToTerminal.bind(button, code, target))
    return button
  }

  function showClickFeedback (button) {
    if (button.classList.contains('clicked')) return
    button.classList.add('clicked')
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { button.classList.remove('clicked') })
    })
  }

  function showErrorFeedback (button) {
    const toast = button.querySelector('.paste-toast')
    if (!toast) return
    toast.textContent = 'Not executed!'
    button.classList.add('clicked', 'error')
    window.setTimeout(function () {
      button.classList.remove('clicked', 'error')
      toast.textContent = 'Executed!'
    }, 1100)
  }

  function writeToClipboard (code) {
    const text = code.innerText.replace(TRAILING_SPACE_RX, '')
    if (window.navigator.clipboard) {
      window.navigator.clipboard.writeText(text).then(showClickFeedback.bind(null, this), fallbackCopy.bind(null, text, this))
    } else {
      fallbackCopy(text, this)
    }
  }

  function fallbackCopy (text, button) {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    try {
      document.execCommand('copy')
      showClickFeedback(button)
    } finally {
      document.body.removeChild(textarea)
    }
  }

  function pasteToTerminal (code, target) {
    const text = code.innerText.replace(TRAILING_SPACE_RX, '')
    try {
      const parentDoc = window.parent.document
      let iframe
      if (target === 'bottom') iframe = parentDoc.querySelector('.tabcontent.active .split.bottom iframe')
      if (!iframe) iframe = parentDoc.querySelector('.tabcontent.active .main-content')
      if (!iframe || !iframe.contentDocument) throw new Error('Terminal iframe not accessible')
      const textarea = iframe.contentDocument.querySelector('.xterm-helper-textarea') || iframe.contentDocument.querySelector('textarea')
      if (!textarea) throw new Error('Terminal textarea not found')
      textarea.focus()
      textarea.dispatchEvent(new InputEvent('input', { bubbles: true, cancelable: true, data: text, inputType: 'insertText' }))
      textarea.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }))
      showClickFeedback(this)
    } catch (error) {
      console.error('Failed to execute code in terminal:', error)
      showErrorFeedback(this)
    }
  }
})()
