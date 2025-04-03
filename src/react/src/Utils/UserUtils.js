const isLigoUser = (user) => {
    return user.authenticationMethod === 'ligo_shibboleth';
};

export { isLigoUser };
