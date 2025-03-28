let user = {
  isAuthenticated: false,
  name: '',
  authenticationMethod: null,
  pk: null,
};

export function getSessionUser() {
  return user;
}

export function setSessionUser(newUser) {
  user = newUser;
}

window.user = user;
