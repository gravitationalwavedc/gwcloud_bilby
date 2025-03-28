import React from 'react';
import Menu from './Components/Menu';

import { getSessionUser, setSessionUser } from './sessionUser';
import { createFragmentContainer } from 'react-relay';
import { graphql } from 'react-relay';

const Layout = ({ children, data }) => {

  console.log("Layout renderr")
  setSessionUser(data.sessionUser)
  const sessionUser = getSessionUser()

  return (
    <>
      <header><Menu name={sessionUser.name} /></header>
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
