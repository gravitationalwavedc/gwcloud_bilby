import Menu from './Components/Menu';

import { UserContext } from './sessionUser';
import { createFragmentContainer } from 'react-relay';
import { graphql } from 'react-relay';

const Layout = ({ children, data }) => {
    return (
        <UserContext.Provider value={data.sessionUser}>
            <header>
                <Menu name={data.sessionUser.name} />
            </header>
            <main className="h-100" style={{ paddingTop: '64px' }}>
                {children}
            </main>
        </UserContext.Provider>
    );
};

export default createFragmentContainer(Layout, {
    data: graphql`
        fragment Layout_sessionUser on Query {
            sessionUser {
                pk
                name
                authenticationMethod
                isAuthenticated
            }
        }
    `,
});
