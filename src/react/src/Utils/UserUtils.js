import { harnessApi } from '../index';

const isLigoUser = () => harnessApi && harnessApi.currentUser && harnessApi.currentUser.isLigoUser;

export { isLigoUser };
