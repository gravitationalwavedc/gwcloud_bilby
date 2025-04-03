import React from 'react';
import { Button } from 'react-bootstrap';
import { HiOutlinePlus } from 'react-icons/hi';

const CustomToggle = React.forwardRef(({ children, onClick }, ref) => (
    <Button variant="link" className="p-0" ref={ref} onClick={(e) => onClick(e)}>
        {children}
        <HiOutlinePlus />
    </Button>
));

CustomToggle.displayName = 'CustomToggle';

export default CustomToggle;
