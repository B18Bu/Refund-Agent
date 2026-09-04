import '@testing-library/jest-dom/vitest'

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

const getComputedStyleWithoutPseudo = window.getComputedStyle.bind(window)
window.getComputedStyle = ((element: Element) => getComputedStyleWithoutPseudo(element)) as typeof window.getComputedStyle
