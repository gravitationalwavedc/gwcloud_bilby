import React from 'react';
import Menu from './Components/Menu';

import { createFragmentContainer } from 'react-relay';
import { graphql } from 'react-relay';
const Layout = ({ children, data }) => {

  const { sessionUser: user } = data
  return (
    <>
      <header><Menu name={user.name} /></header>
      <main className="h-100" style={{ paddingTop: '64px' }}>
        {children}
      </main >
    </>)
}


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
    `
});
