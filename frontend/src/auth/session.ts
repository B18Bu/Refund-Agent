export const getSessionToken = () => sessionStorage.getItem('token')
export const setSessionToken = (token: string) => sessionStorage.setItem('token', token)
export const clearSessionToken = () => sessionStorage.removeItem('token')
