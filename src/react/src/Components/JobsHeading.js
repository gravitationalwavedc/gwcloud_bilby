import React from 'react';
import { Button } from 'react-bootstrap';
import { HiOutlinePlus } from 'react-icons/hi';
import Link from 'found/Link';

const JobsHeading = ({ match, router, heading, link }) => 
    <h1 className="pt-5 mb-4">
        { heading }
        <span className="float-right">
            <Link 
                as={Button}
                variant="outline-primary"
                to={link.path}
                exact 
                match={match} 
                router={router} 
                className="mr-1">
                {link.text}
            </Link>
            <Link as={Button} to='/bilby/job-form/' exact match={match} router={router}>
                <HiOutlinePlus size={18} className="mb-1 mr-1"/>
                    Start a new job 
            </Link>
        </span>
    </h1>;

export default JobsHeading;
