import { getSessionUser } from '../sessionUser'

const isLigoUser = () => {
  return getSessionUser().authenticationMethod === 'ligo_shibboleth';
};

export { isLigoUser };
