import React from 'react';
import JobBadges from './JobBadges';
import { Badge } from 'react-bootstrap';
import Link from 'found/Link';

const JobTableBody = ({data, myJobs, match, router}) => 
    <tbody>
        {data && data.edges.length > 0 ? 
            data.edges.map(({node}) => 
                <tr key={node.id}>
                    {!myJobs && <td>{node.user}</td>}
                    <td>{node.name}</td>
                    <td>{node.description}</td>
                    <td className="text-center">
                        <Badge 
                            key={node.jobStatus.name } 
                            variant="primary"
                            pill>
                            {node.jobStatus.name}
                        </Badge>
                    </td>
                    <td className="text-center">
                        <JobBadges labels={node.labels} />
                    </td>
                    <td className="text-center">
                        <Link 
                            key={node.id}
                            size="sm" 
                            variant="outline-primary" 
                            to={{pathname: '/bilby/job-results/' + node.id + '/'}} 
                            activeClassName="selected" 
                            exact 
                            match={match} 
                            router={router}>
                              View
                        </Link>
                    </td>
                </tr>) : 
            <tr>
                <td colSpan='5'>Create a new job or try searching `&apos`Any time`&apos`.</td>
            </tr>
        }
    </tbody>;

export default JobTableBody;
