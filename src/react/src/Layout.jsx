import React from 'react';
import Menu from './Components/Menu';

const Layout = ({ children }) => {
  return (
    <>
      <header><Menu name="test" /></header>
      <main className="h-100" style={{ paddingTop: '64px' }}>
        {children}
      </main >
    </>)
}

export default Layout;
